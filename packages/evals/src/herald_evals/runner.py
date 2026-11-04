"""Run each case through the real triage graph and keep everything it produced.

The graph is the product's own (`build_graph` + `triage`), so the eval measures word check,
history, notes, rule verdicts and the decide step together. History comes from the case
instead of a database, through the same `Toolbox` the server uses.
"""

import asyncio
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from herald_core.graph import build_graph, triage
from herald_core.history import (
    RECENT_CORRECTIONS,
    SENDER_HISTORY,
    THREAD,
    CorrectionsIn,
    History,
    SenderHistoryIn,
    ThreadIn,
)
from herald_core.model import ModelError, TriageModel
from herald_core.schema import Decision, Email, Notes, RiskFlag, RuleVerdict, WorkspaceConfig
from herald_core.tools import Toolbox
from herald_evals.dataset import Case, Dataset
from herald_server.tracing import NO_TRACING, Tracing, record_outcome


class Trial(BaseModel):
    """One run of one case."""

    dataset: str
    case_id: str
    run: int
    notes: Notes | None
    verdicts: list[RuleVerdict]
    word_flags: list[RiskFlag]
    decision: Decision
    errors: list[str] = Field(default_factory=list)
    # The model tools the AI chose to call, as "node:tool" (see EmailContext.asked).
    asked: list[str] = Field(default_factory=list)
    ms: int
    # Set when the run was traced; the CLI scores the trace with `passed` once labels are checked.
    trace_id: str | None = None


class RecordingModel:
    """Passes every call through and keeps the failures.

    The graph swallows a `ModelError` on purpose (the email goes to "Needs a look"). In an
    eval that would score a rate limit or a timeout as the AI being unsure, or as a missed
    alert, so each failure is kept here and the trial is reported as a model error instead.
    """

    def __init__(self, inner: TriageModel) -> None:
        self._inner = inner
        self.errors: list[str] = []

    async def write_notes(self, email, business_name, config, history=None, tools=()) -> Notes:
        try:
            return await self._inner.write_notes(email, business_name, config, history, tools)
        except ModelError as exc:
            self.errors.append(f"write_notes: {exc}")
            raise

    async def judge_rules(
        self, email, business_name, config, history=None, tools=()
    ) -> list[RuleVerdict]:
        try:
            return await self._inner.judge_rules(email, business_name, config, history, tools)
        except ModelError as exc:
            self.errors.append(f"judge_rules: {exc}")
            raise

    async def suggest_setup(self, name, description):
        return await self._inner.suggest_setup(name, description)


class _Recorded:
    """A history tool that answers with what the case recorded."""

    description = "History recorded in an eval case."

    def __init__(self, name: str, input_model: type[BaseModel], output: BaseModel) -> None:
        self.name = name
        self.input_model = input_model
        self.output_model = type(output)
        self._output = output

    async def run(self, args: BaseModel) -> BaseModel:
        return self._output


def _toolbox(history: History) -> Toolbox:
    tools = []
    if history.sender:
        tools.append(_Recorded(SENDER_HISTORY, SenderHistoryIn, history.sender))
    if history.thread:
        tools.append(_Recorded(THREAD, ThreadIn, history.thread))
    if history.corrections:
        tools.append(_Recorded(RECENT_CORRECTIONS, CorrectionsIn, history.corrections))
    return Toolbox(tools)


async def run_case(
    model: TriageModel,
    dataset: Dataset,
    case: Case,
    run: int,
    now: datetime,
    tracing: Tracing = NO_TRACING,
    session: str = "",
) -> Trial:
    recorder = RecordingModel(model)
    # Compiling is cheap, and a graph per trial keeps each trial's errors on its own recorder.
    # The tracing wraps the recorder, so a ModelError still reaches the recorder first.
    graph = build_graph(tracing.wrap_model(recorder))
    email: Email = case.email(workspace_id=f"eval-{dataset.name}")
    history = case.history.build(case.id, now) if case.history else History()
    config: WorkspaceConfig = dataset.config
    started = time.perf_counter()
    with tracing.run(
        "eval",
        user_id=f"eval-{dataset.name}",
        session_id=session,
        tags=["eval", dataset.name],
        metadata={"case": case.id, "run": str(run)},
    ) as traced:
        state = await triage(
            graph,
            email,
            config,
            business_name=dataset.business,
            tools=_toolbox(history),
            callbacks=traced.callbacks,
        )
        record_outcome(tracing, traced, state["decision"], state.get("notes"))
    # The node's deadline cancels the call inside the recorder, so a timeout reaches only the
    # state. Count it too, or a slow API would be scored as the AI's judgement.
    recorded = {error.split(":", 1)[0] for error in recorder.errors}
    errors = recorder.errors + [
        f"{failure.call}: {failure.error}"
        for failure in state.get("ai_failures", [])
        if failure.call not in recorded
    ]
    return Trial(
        dataset=dataset.name,
        case_id=case.id,
        run=run,
        notes=state.get("notes"),
        # None when the rules call failed; that trial is a model error, not a verdict.
        verdicts=state.get("verdicts") or [],
        word_flags=sorted(state.get("word_flags", set())),
        decision=state["decision"],
        errors=errors,
        asked=state.get("asked", []),
        ms=round((time.perf_counter() - started) * 1000),
        trace_id=traced.trace_id,
    )


async def run_all(
    model: TriageModel,
    work: Sequence[tuple[Dataset, Case]],
    *,
    repeats: int = 1,
    concurrency: int = 4,
    progress: Callable[[str], None] | None = None,
    tracing: Tracing = NO_TRACING,
    session: str = "",
) -> list[Trial]:
    # A small cap keeps a run under the API's rate limits; the client retries what slips past.
    gate = asyncio.Semaphore(concurrency)
    now = datetime.now(UTC)
    total = len(work) * repeats
    done = 0

    async def one(dataset: Dataset, case: Case, run: int) -> Trial:
        nonlocal done
        async with gate:
            trial = await run_case(model, dataset, case, run, now, tracing, session)
        done += 1
        if progress:
            mark = "!" if trial.errors else "."
            progress(f"[{done}/{total}] {mark} {dataset.name}/{case.id} -> {trial.decision.route}")
        return trial

    jobs = [one(d, c, r) for r in range(repeats) for d, c in work]
    return list(await asyncio.gather(*jobs))


def stderr(line: str) -> None:
    print(line, file=sys.stderr, flush=True)
