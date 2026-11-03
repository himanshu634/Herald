import logging
import sys
from contextlib import contextmanager

import pytest
from pydantic import SecretStr

import herald_server.tracing as tracing_module
from herald_core.model import FakeModel, ModelError
from herald_core.schema import Decision, Email, Notes, RiskFlag, Route, WorkspaceConfig
from herald_server.tracing import (
    NO_TRACING,
    LangfuseTracing,
    Run,
    TracedModel,
    build_tracing,
    record_outcome,
)

EMAIL = Email(id="e1", workspace_id="w1", sender="a@b.example", subject="Hi", body="Hello")
CONFIG = WorkspaceConfig(business_profile="Online luggage brand.", topics=["Orders and delivery"])


class StubClient:
    """Stands in for the Langfuse client. Records what it is asked to do.

    With raise_all=True every method raises, to prove a Langfuse failure never reaches triage.
    """

    def __init__(self, raise_all: bool = False) -> None:
        self.raise_all = raise_all
        self.spans: list[str] = []
        self.scores: list[tuple[str, str, str | bool]] = []
        self.trace_id = "t1"

    def _maybe_raise(self) -> None:
        if self.raise_all:
            raise RuntimeError("langfuse is down")

    @contextmanager
    def start_as_current_observation(self, *, as_type: str, name: str):
        self._maybe_raise()
        self.spans.append(name)
        yield object()

    def get_current_trace_id(self) -> str:
        self._maybe_raise()
        return self.trace_id

    def create_score(self, *, name, value, trace_id, data_type) -> None:
        self._maybe_raise()
        self.scores.append((trace_id, name, value))


propagated: list[dict] = []


@contextmanager
def stub_propagate(**kwargs):
    """Stands in for langfuse.propagate_attributes and records its keyword arguments."""
    propagated.append(kwargs)
    yield


class FailingModel(FakeModel):
    async def write_notes(self, *args, **kwargs):
        raise ModelError("rate limited")


class BrokenSpanClient(StubClient):
    """Opening a span fails; the model must still be called."""

    def __init__(self) -> None:
        super().__init__(raise_all=True)


def keyed(settings, **extra):
    return settings.model_copy(
        update={"langfuse_public_key": "pk", "langfuse_secret_key": SecretStr("sk"), **extra}
    )


def test_tracing_is_off_without_keys(settings):
    assert build_tracing(settings) is NO_TRACING


def test_tracing_is_off_with_empty_keys(settings):
    empty = settings.model_copy(
        update={"langfuse_public_key": "", "langfuse_secret_key": SecretStr("")}
    )
    assert build_tracing(empty) is NO_TRACING


def test_tracing_is_off_when_langfuse_is_missing(settings, monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "langfuse", None)  # import raises ImportError
    assert build_tracing(keyed(settings)) is NO_TRACING
    assert "langfuse is not installed" in caplog.text


def test_tracing_is_off_when_langfuse_is_down(settings, caplog):
    down = keyed(settings, langfuse_base_url="http://127.0.0.1:9")  # nothing listens here
    assert build_tracing(down) is NO_TRACING
    # One warning, not one per email. Count only Herald's records: the SDK logs on its own.
    assert len([r for r in caplog.records if r.name == "herald_server.tracing"]) == 1
    assert not tracing_module._instrumented  # anthropic stays unpatched for the rest of the session


async def test_traced_model_passes_calls_through():
    client = StubClient()
    traced = TracedModel(FakeModel(), client)
    notes = await traced.write_notes(EMAIL, "Tripfold", CONFIG)
    assert notes == await FakeModel().write_notes(EMAIL, "Tripfold", CONFIG)
    await traced.judge_rules(EMAIL, "Tripfold", CONFIG)
    assert client.spans == ["model.write_notes", "model.judge_rules"]


async def test_traced_model_passes_errors_through():
    traced = TracedModel(FailingModel(), StubClient())
    with pytest.raises(ModelError):
        await traced.write_notes(EMAIL, "Tripfold", CONFIG)


async def test_traced_model_calls_inner_when_the_span_fails(caplog):
    traced = TracedModel(FakeModel(), BrokenSpanClient())
    notes = await traced.write_notes(EMAIL, "Tripfold", CONFIG)
    assert notes == await FakeModel().write_notes(EMAIL, "Tripfold", CONFIG)
    # A real model error is still raised unchanged when the span is broken too.
    with pytest.raises(ModelError):
        await TracedModel(FailingModel(), BrokenSpanClient()).write_notes(EMAIL, "T", CONFIG)


def test_outcome_scores():
    client = StubClient()
    tracing = LangfuseTracing(
        client, model_name="claude-haiku-5-5", propagate=stub_propagate, handler=object
    )
    decision = Decision(
        route=Route.ALERT, urgency=None, reason="floor", floor_flags=[RiskFlag.LEGAL_THREAT]
    )
    record_outcome(tracing, Run("t1", []), decision, notes=None)
    assert client.scores == [
        ("t1", "route", "alert"),
        ("t1", "floor", True),
        ("t1", "unsure", False),
        ("t1", "ai_failed", True),
    ]


def test_outcome_scores_with_unsure_notes():
    client = StubClient()
    tracing = LangfuseTracing(client, "m", stub_propagate, object)
    decision = Decision(route=Route.NEEDS_A_LOOK, urgency=None, reason="unsure")
    notes = Notes(topic="x", urgency="low", anger=1, summary="s", sure=False, question="q?")
    record_outcome(tracing, Run("t1", []), decision, notes)
    assert client.scores[1:] == [
        ("t1", "floor", False),
        ("t1", "unsure", True),
        ("t1", "ai_failed", False),
    ]


def test_run_opens_a_trace_with_attributes():
    client = StubClient()
    tracing = LangfuseTracing(client, "claude-haiku-5-5", stub_propagate, lambda **kw: kw)
    propagated.clear()
    with tracing.run(
        "email", user_id="w1", session_id="e1", tags=["a"], metadata={"k": "v"}
    ) as run:
        assert run.trace_id == "t1"
        assert len(run.callbacks) == 1
    assert client.spans == ["email"]
    assert propagated[0]["tags"] == ["a", "claude-haiku-5-5"]
    assert propagated[0]["user_id"] == "w1"


def test_run_survives_a_failing_client():
    tracing = LangfuseTracing(StubClient(raise_all=True), "m", stub_propagate, object)
    with tracing.run("email", user_id="w", session_id="e", tags=[], metadata={}) as run:
        assert run == Run(None, [])


def test_run_does_not_swallow_errors_from_its_body():
    tracing = LangfuseTracing(StubClient(), "m", stub_propagate, object)
    with pytest.raises(ValueError):
        with tracing.run("email", user_id="w", session_id="e", tags=[], metadata={}):
            raise ValueError("boom")


def test_score_swallows_client_errors(caplog):
    tracing = LangfuseTracing(StubClient(raise_all=True), "m", stub_propagate, object)
    with caplog.at_level(logging.WARNING):
        tracing.score("t1", "route", "alert")
    assert "t1" in caplog.text or "route" in caplog.text


def test_no_tracing_does_nothing():
    model = FakeModel()
    assert NO_TRACING.wrap_model(model) is model
    with NO_TRACING.run("x", user_id="u", session_id="s", tags=[], metadata={}) as run:
        assert run == Run(None, [])
    NO_TRACING.score(None, "route", "alert")
    NO_TRACING.shutdown()
