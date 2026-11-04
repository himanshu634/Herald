"""Dev-only tracing to Langfuse. This is the only file that knows Langfuse.

Langfuse sits in the uv dev group, so it is imported lazily and tracing is off wherever it is
missing (the production image). Tracing must never change what triage does: every Langfuse call
here catches its own errors, and a model error from the inner model passes through unchanged.
"""

import logging
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any, Protocol

from herald_core.history import History
from herald_core.model import TriageModel
from herald_core.schema import Decision, Email, Notes, RuleVerdict, SetupDraft, WorkspaceConfig
from herald_server.settings import Settings

log = logging.getLogger(__name__)

# Anthropic is patched once per process. create_app runs once per test and on every reload,
# and instrumenting twice would wrap `parse` twice and log every call twice.
_instrumented = False


class _Safe:
    """Wraps a Langfuse context manager so a failure on exit is logged, never raised.

    Without it, an error while closing a span would replace the caller's result (or its own
    exception) and break triage. A body exception still propagates unchanged.
    """

    def __init__(self, cm: Any) -> None:
        self._cm = cm

    def __enter__(self) -> Any:
        return self._cm.__enter__()

    def __exit__(self, *exc_info: Any) -> bool:
        try:
            return bool(self._cm.__exit__(*exc_info))
        except Exception as exc:
            log.warning("Tracing: could not close a span: %s", exc)
            return False


@dataclass
class Run:
    """What one traced triage run hands to the graph: the trace id and its callbacks."""

    trace_id: str | None
    callbacks: list[Any]


class Tracing(Protocol):
    enabled: bool

    def wrap_model(self, model: TriageModel) -> TriageModel: ...

    # A sync context manager: callers hold it open around an `await`.
    def run(
        self,
        name: str,
        *,
        user_id: str,
        session_id: str,
        tags: list[str],
        metadata: dict[str, str],
    ) -> AbstractContextManager[Run]: ...

    def score(self, trace_id: str | None, name: str, value: str | bool) -> None: ...

    def shutdown(self) -> None: ...


class _NoTracing:
    enabled = False

    def wrap_model(self, model: TriageModel) -> TriageModel:
        return model

    @contextmanager
    def run(self, name, *, user_id, session_id, tags, metadata):
        yield Run(None, [])

    def score(self, trace_id: str | None, name: str, value: str | bool) -> None:
        pass

    def shutdown(self) -> None:
        pass


NO_TRACING: Tracing = _NoTracing()


class TracedModel:
    """Runs write_notes and judge_rules inside a span each, and passes everything through.

    If the span cannot open, the call runs untraced. The inner call is never inside the
    try that guards the span, so the inner model's own errors (a ModelError, say) reach the
    graph exactly as they would without tracing.
    """

    def __init__(self, inner: TriageModel, client: Any) -> None:
        self._inner = inner
        self._client = client

    async def _in_span(self, name: str, call):
        stack = ExitStack()
        try:
            stack.enter_context(
                _Safe(self._client.start_as_current_observation(as_type="span", name=name))
            )
        except Exception as exc:
            log.warning("Tracing: could not open span %s, running untraced: %s", name, exc)
            stack = None
        # Awaited outside the except block, so a ModelError does not carry the tracing error
        # as its __context__.
        if stack is None:
            return await call()
        with stack:
            return await call()

    async def write_notes(
        self,
        email: Email,
        business_name: str,
        config: WorkspaceConfig,
        history: History | None = None,
    ) -> Notes:
        return await self._in_span(
            "model.write_notes",
            lambda: self._inner.write_notes(email, business_name, config, history),
        )

    async def judge_rules(
        self,
        email: Email,
        business_name: str,
        config: WorkspaceConfig,
        history: History | None = None,
    ) -> list[RuleVerdict]:
        return await self._in_span(
            "model.judge_rules",
            lambda: self._inner.judge_rules(email, business_name, config, history),
        )

    async def suggest_setup(self, name: str, description: str) -> SetupDraft:
        return await self._inner.suggest_setup(name, description)


class LangfuseTracing:
    """Tracing backed by a Langfuse client.

    `propagate` is langfuse.propagate_attributes and `handler` is the LangChain CallbackHandler
    class. They are passed in so tests can stub them and never touch the SDK.
    """

    enabled = True

    def __init__(
        self,
        client: Any,
        model_name: str,
        propagate: Any,
        handler: Any,
        public_key: str | None = None,
    ) -> None:
        self._client = client
        self._model_name = model_name
        self._propagate = propagate
        self._handler = handler
        self._public_key = public_key

    def wrap_model(self, model: TriageModel) -> TriageModel:
        return TracedModel(model, self._client)

    @contextmanager
    def run(self, name, *, user_id, session_id, tags, metadata):
        stack = ExitStack()
        try:
            stack.enter_context(
                _Safe(
                    self._propagate(
                        trace_name=name,
                        user_id=user_id,
                        session_id=session_id,
                        tags=[*tags, self._model_name],
                        metadata=metadata,
                    )
                )
            )
            stack.enter_context(
                _Safe(self._client.start_as_current_observation(as_type="span", name=name))
            )
            # The handler is given the public key because Herald never sets LANGFUSE_* env vars,
            # so the SDK could not otherwise tell which client to use.
            run = Run(
                trace_id=self._client.get_current_trace_id(),
                callbacks=[self._handler(public_key=self._public_key)],
            )
        except Exception as exc:
            log.warning("Tracing: could not open trace %s, running untraced: %s", name, exc)
            stack.close()
            run = Run(None, [])
        # Outside the try above: an error raised by the caller's body must propagate.
        with stack:
            yield run

    def score(self, trace_id: str | None, name: str, value: str | bool) -> None:
        if trace_id is None:
            return
        try:
            if isinstance(value, bool):
                self._client.create_score(
                    name=name, value=1 if value else 0, trace_id=trace_id, data_type="BOOLEAN"
                )
            else:
                self._client.create_score(
                    name=name, value=value, trace_id=trace_id, data_type="CATEGORICAL"
                )
        except Exception as exc:
            log.warning("Tracing: could not post score %s for trace %s: %s", name, trace_id, exc)

    def shutdown(self) -> None:
        # Flushes queued spans so a short-lived process does not drop its last traces.
        try:
            self._client.shutdown()
        except Exception as exc:
            log.warning("Tracing: shutdown failed: %s", exc)


def _shutdown_quietly(client: Any) -> None:
    # Stops the client's exporter thread so it does not keep running for nothing.
    try:
        client.shutdown()
    except Exception:
        pass


def build_tracing(settings: Settings) -> Tracing:
    """Tracing when both keys are set and Langfuse answers, otherwise NO_TRACING."""
    # An empty string counts as unset: the test conftest blanks the keys.
    public_key = settings.langfuse_public_key
    secret = settings.langfuse_secret_key.get_secret_value() if settings.langfuse_secret_key else ""
    if not public_key or not secret:
        log.info("Langfuse keys are not set; tracing is off")
        return NO_TRACING

    # Lazy: the production image has no dev group, so these imports must not run at module load.
    try:
        from langfuse import Langfuse, propagate_attributes
        from langfuse.langchain import CallbackHandler
        from openinference.instrumentation.anthropic import AnthropicInstrumentor
    except ImportError:
        log.warning("langfuse is not installed; tracing is off")
        return NO_TRACING

    client = None
    try:
        client = Langfuse(
            public_key=public_key, secret_key=secret, base_url=settings.langfuse_base_url
        )
        ok = client.auth_check()
    except Exception as exc:
        ok, why = False, f"{type(exc).__name__}: {exc}"
    else:
        why = "auth_check returned False"
    if not ok:
        if client is not None:
            _shutdown_quietly(client)
        log.warning(
            "Langfuse at %s did not accept the keys or is not reachable (%s); tracing is off",
            settings.langfuse_base_url,
            why,
        )
        return NO_TRACING

    # Only after auth succeeds, so a down Langfuse leaves Anthropic unpatched.
    global _instrumented
    if not _instrumented:
        try:
            AnthropicInstrumentor().instrument()
        except Exception as exc:
            # Dev tooling must not stop the API or worker from starting.
            _shutdown_quietly(client)
            log.warning("Tracing: could not instrument Anthropic, tracing is off: %s", exc)
            return NO_TRACING
        _instrumented = True
    # The tag names the model that runs. Fake runs (lite mode, evals) must not carry the
    # Claude name from settings.
    model_name = settings.model_name if settings.model_provider == "anthropic" else "fake"
    log.info("Tracing to Langfuse at %s", settings.langfuse_base_url)
    return LangfuseTracing(
        client, model_name, propagate_attributes, CallbackHandler, public_key=public_key
    )


def record_outcome(tracing: Tracing, run: Run, decision: Decision, notes: Notes | None) -> None:
    """Post what Herald decided as scores on the trace, so runs can be filtered by outcome."""
    tracing.score(run.trace_id, "route", str(decision.route.value))
    tracing.score(run.trace_id, "floor", bool(decision.floor_flags))
    tracing.score(run.trace_id, "unsure", notes is not None and not notes.sure)
    tracing.score(run.trace_id, "ai_failed", notes is None)
