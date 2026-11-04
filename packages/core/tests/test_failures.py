"""Model failures: how each error is sorted, and what the graph does with it."""

import asyncio
from types import SimpleNamespace

import httpx2
import openai
import pytest
from anthropic import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OverloadedError,
    RateLimitError,
)

from herald_core import graph
from herald_core.graph import build_graph, triage
from herald_core.model import (
    REQUEST_RETRIES,
    REQUEST_TIMEOUT,
    SETUP_TIMEOUT,
    ModelError,
    failure_kind,
    failure_of,
    status_kind,
)
from herald_core.providers import anthropic as anthropic_provider
from herald_core.providers import openrouter as openrouter_provider
from herald_core.providers.anthropic import AnthropicModel
from herald_core.providers.openrouter import OpenRouterModel
from herald_core.schema import Email, FailureKind, Route, Rule, RuleAction, WorkspaceConfig
from scripted_model import ScriptedModel

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

CONFIG = WorkspaceConfig(
    business_profile="Online luggage brand.",
    topics=["Orders and delivery"],
    rules=[Rule(id="r-close", name="Close all", when="any email", action=RuleAction.CLOSE)],
)


def status_error(cls, code: int, headers: dict[str, str] | None = None):
    response = httpx2.Response(code, headers=headers or {}, request=REQUEST)
    return cls("refused", response=response, body=None)


def email(body: str = "Where is my order?") -> Email:
    return Email(id="e1", workspace_id="w1", sender="a@customer.in", subject="Order", body=body)


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (status_error(RateLimitError, 429), FailureKind.UNAVAILABLE),
        (status_error(OverloadedError, 529), FailureKind.UNAVAILABLE),
        (status_error(InternalServerError, 500), FailureKind.UNAVAILABLE),
        (APIConnectionError(request=REQUEST), FailureKind.UNAVAILABLE),
        (APITimeoutError(request=REQUEST), FailureKind.UNAVAILABLE),
        (status_error(AuthenticationError, 401), FailureKind.SETUP),
        (status_error(NotFoundError, 404), FailureKind.SETUP),
        (status_error(BadRequestError, 400), FailureKind.UNREADABLE),
    ],
)
def test_anthropic_errors_are_sorted_by_what_a_retry_can_fix(error, kind):
    assert anthropic_provider.error_kind(error) is kind


OR_REQUEST = httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def or_status_error(cls, code: int):
    return cls("refused", response=httpx2.Response(code, request=OR_REQUEST), body=None)


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (or_status_error(openai.RateLimitError, 429), FailureKind.UNAVAILABLE),
        (or_status_error(openai.InternalServerError, 502), FailureKind.UNAVAILABLE),
        (openai.APITimeoutError(request=OR_REQUEST), FailureKind.UNAVAILABLE),
        (or_status_error(openai.APIStatusError, 402), FailureKind.SETUP),  # out of credits
        (or_status_error(openai.AuthenticationError, 401), FailureKind.SETUP),
        (or_status_error(openai.BadRequestError, 400), FailureKind.UNREADABLE),
    ],
)
def test_openrouter_errors_are_sorted_by_what_a_retry_can_fix(error, kind):
    assert openrouter_provider.error_kind(error) is kind


@pytest.mark.parametrize(
    ("status", "kind"),
    [(408, FailureKind.UNAVAILABLE), (529, FailureKind.UNAVAILABLE), (403, FailureKind.SETUP)],
)
def test_status_codes_are_sorted_the_same_for_every_provider(status, kind):
    assert status_kind(status) is kind


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (ModelError("down", FailureKind.UNAVAILABLE), FailureKind.UNAVAILABLE),
        (TimeoutError(), FailureKind.UNAVAILABLE),  # a node deadline
        (TypeError("a bug in Herald"), FailureKind.UNREADABLE),
    ],
)
def test_errors_outside_the_sdks_are_sorted(error, kind):
    assert failure_kind(error) is kind


def test_failure_keeps_the_sdk_error_behind_a_model_error():
    try:
        try:
            raise status_error(RateLimitError, 429, {"retry-after": "12"})
        except RateLimitError as exc:
            raise ModelError(str(exc), anthropic_provider.error_kind(exc)) from exc
    except ModelError as wrapped:
        failure = failure_of("write_notes", wrapped)
    assert failure.kind is FailureKind.UNAVAILABLE
    assert failure.error == "RateLimitError"
    assert failure.retry_after == 12


@pytest.mark.parametrize("model_class", [AnthropicModel, OpenRouterModel])
def test_client_fits_inside_the_job_timeout(model_class):
    client = model_class(api_key="test")._client
    assert client.max_retries == REQUEST_RETRIES
    assert client.timeout.read == REQUEST_TIMEOUT


async def test_setup_draft_gets_longer_than_triage():
    calls = []

    async def parse(**kwargs):
        calls.append(kwargs)
        raise status_error(OverloadedError, 529)

    model = AnthropicModel(client=SimpleNamespace(messages=SimpleNamespace(parse=parse)))  # type: ignore[arg-type]
    with pytest.raises(ModelError):
        await model.suggest_setup("Tripfold", "Luggage")
    with pytest.raises(ModelError):
        await model.write_notes(email(), "Tripfold", CONFIG)
    assert calls[0]["timeout"] == SETUP_TIMEOUT
    assert "timeout" not in calls[1]


async def test_parse_says_an_overload_is_worth_retrying():
    async def parse(**kwargs):
        raise status_error(OverloadedError, 529)

    model = AnthropicModel(client=SimpleNamespace(messages=SimpleNamespace(parse=parse)))  # type: ignore[arg-type]
    with pytest.raises(ModelError) as raised:
        await model.write_notes(email(), "Tripfold", CONFIG)
    assert raised.value.kind is FailureKind.UNAVAILABLE


class DownModel(ScriptedModel):
    async def write_notes(self, email, business_name, config, history=None, tools=()):
        raise ModelError("overloaded", FailureKind.UNAVAILABLE)

    async def judge_rules(self, email, business_name, config, history=None, tools=()):
        raise ModelError("overloaded", FailureKind.UNAVAILABLE)


async def test_an_outage_is_recorded_and_named_to_the_owner():
    state = await triage(build_graph(DownModel()), email(), CONFIG, business_name="Tripfold")
    assert {f.call for f in state["ai_failures"]} == {"write_notes", "judge_rules"}
    assert {f.kind for f in state["ai_failures"]} == {FailureKind.UNAVAILABLE}
    assert state["decision"].route is Route.NEEDS_A_LOOK
    assert state["decision"].reason == "The AI was unavailable"


async def test_an_outage_never_stops_the_safety_floor():
    state = await triage(
        build_graph(DownModel()),
        email("I will take legal action against you."),
        CONFIG,
        business_name="Tripfold",
    )
    assert state["decision"].route is Route.ALERT


class RulesDownModel(ScriptedModel):
    async def judge_rules(self, email, business_name, config, history=None, tools=()):
        raise ModelError("overloaded", FailureKind.UNAVAILABLE)


async def test_failed_rules_call_is_not_read_as_no_rule_matched():
    state = await triage(build_graph(RulesDownModel()), email(), CONFIG, business_name="Tripfold")
    assert state["notes"] is not None
    assert state["verdicts"] is None
    assert [f.call for f in state["ai_failures"]] == ["judge_rules"]
    assert state["decision"].route is Route.NEEDS_A_LOOK
    assert state["decision"].reason == "Your rules could not be checked"


class SlowModel(ScriptedModel):
    async def write_notes(self, email, business_name, config, history=None, tools=()):
        await asyncio.sleep(5)
        raise AssertionError("the deadline should have stopped this call")

    async def judge_rules(self, email, business_name, config, history=None, tools=()):
        await asyncio.sleep(5)
        raise AssertionError("the deadline should have stopped this call")


async def test_a_slow_call_is_cut_off_and_counts_as_unavailable(monkeypatch):
    monkeypatch.setattr(graph, "MODEL_DEADLINE", 0.01)
    state = await triage(build_graph(SlowModel()), email(), CONFIG, business_name="Tripfold")
    assert {(f.error, f.kind) for f in state["ai_failures"]} == {
        ("TimeoutError", FailureKind.UNAVAILABLE)
    }
    assert state["decision"].route is Route.NEEDS_A_LOOK
