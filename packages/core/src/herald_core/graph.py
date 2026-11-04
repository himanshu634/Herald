"""The triage pipeline as a LangGraph graph: its state, its nodes and the wiring.

    START -> word_check ─────────────────────────┐
    START -> gather_context ┬-> write_notes ─────┼-> decide -> END
                            └-> judge_rules ─────┘

The graph is compiled once and shared by every tenant; each run carries its workspace's
config in the state and its toolbox in the runtime context. `gather_context` runs the history
tools in code before the model reads the email. Thread and corrections go into the prompt;
the sender's history does not; the model calls the sender_history tool for it when it needs
it, and decide always gets it for the repeat count. `word_check` starts from START and never
waits on tools; both model nodes wait on `gather_context`, so a slow tool can delay the alert
by at most the tool timeout (2 s). The two model calls run side by side: the rules prompt never
reads the notes, and running them one after the other doubled the time to decide. A model tool
call adds one more model call to write_notes or judge_rules, which decide also waits on.

The nodes only adapt state: the word check lives in `safety.py` and the routing in `decide.py`.
Each node logs one line keyed by email id, so runs of parallel emails can be told apart. Only
ids, enums, counts and timings: never the sender, subject, body or the model's free text.
"""

import asyncio
import logging
import operator
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from herald_core.decide import decide
from herald_core.history import (
    RECENT_CORRECTIONS,
    SENDER_HISTORY,
    THREAD,
    Corrections,
    CorrectionsIn,
    History,
    SenderHistory,
    SenderHistoryIn,
    Thread,
    ThreadIn,
)
from herald_core.model import MODEL_DEADLINE, TriageModel, failure_of
from herald_core.safety import word_check
from herald_core.schema import (
    AiFailure,
    Decision,
    Email,
    FailureKind,
    Notes,
    RiskFlag,
    RuleVerdict,
    WorkspaceConfig,
)
from herald_core.tools import SenderLookup, Toolbox, asked

log = logging.getLogger(__name__)


@dataclass
class TriageContext:
    """Per-run objects that are not state: the toolbox is bound to one workspace by the server."""

    tools: Toolbox


class TriageState(TypedDict, total=False):
    """Parallel nodes write different keys, except `asked` and `ai_failures`, which
    write_notes and judge_rules both write and a reducer joins. Add a reducer before letting
    two parallel nodes write any other key, or LangGraph rejects the run."""

    email: Email
    config: WorkspaceConfig
    business_name: str
    word_flags: set[RiskFlag]
    history: History
    # The model tools the AI chose to call, as "node:tool". Each model node returns only its own
    # calls and the reducer appends them, so neither node overwrites the other's.
    asked: Annotated[list[str], operator.add]
    notes: Notes | None
    # None when the rules call failed, so a failure never reads as "no rule matched".
    verdicts: list[RuleVerdict] | None
    # One entry per model call that gave no answer. Each node returns only its own.
    ai_failures: Annotated[list[AiFailure], operator.add]
    decision: Decision


def _names(items: Iterable[str]) -> str:
    return ",".join(sorted(items)) or "none"


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def run_word_check(state: TriageState) -> TriageState:
    """The safety floor: a regex word check that never waits on tools or AI."""
    email = state["email"]
    flags = word_check(f"{email.subject}\n{email.body}")
    log.info("email %s word_check: flags=%s", email.id, _names(flags))
    return {"word_flags": flags}


async def gather_context(state: TriageState, runtime: Runtime[TriageContext]) -> TriageState:
    """Runs the history tools in code, no AI, before the model reads the email."""
    tools = runtime.context.tools
    email = state["email"]
    calls = [
        tools.call(SENDER_HISTORY, SenderHistoryIn(sender=email.sender)),
        tools.call(RECENT_CORRECTIONS, CorrectionsIn()),
    ]
    if email.thread_id:
        calls.append(tools.call(THREAD, ThreadIn(thread_id=email.thread_id)))
    # Toolbox.call never raises, so one bad tool cannot cancel the others.
    results = await asyncio.gather(*calls)
    # Keep only the type each slot expects; anything else counts as "no history".
    sender = next((r for r in results if isinstance(r, SenderHistory)), None)
    corrections = next((r for r in results if isinstance(r, Corrections)), None)
    thread = next((r for r in results if isinstance(r, Thread)), None)
    log.info(
        "email %s gather_context: sender_30d=%s thread=%s corrections=%s",
        email.id,
        sender.count_30d if sender else "-",
        len(thread.messages) if thread else "-",
        len(corrections.items) if corrections else "-",
    )
    return {"history": History(sender=sender, thread=thread, corrections=corrections)}


def _record_failure(call: str, email_id: str, exc: Exception) -> AiFailure:
    """Sorts a failed model call and logs it once.

    The model nodes never raise. A raise inside the parallel step would stop word_check and
    decide too, and the safety floor would be lost with the notes. The failure goes into state
    instead, and the server decides after decide whether to save the result or try again later.
    """
    failure = failure_of(call, exc)
    message = "%s failed for email %s: %s (%s, request %s)"
    args = (call, email_id, failure.error, failure.kind, failure.request_id)
    if failure.kind is FailureKind.UNAVAILABLE:
        # Expected during an outage, and retried: no traceback per email.
        log.warning(message, *args)
    elif failure.kind is FailureKind.SETUP:
        # Every email will fail this way until someone fixes the key, model or billing.
        log.error(message, *args)
    else:
        log.error(message, *args, exc_info=exc)
    return failure


def _sender_lookup(state: TriageState) -> SenderLookup:
    # A fresh one per node, so each node can report whether its model call used it.
    history = state.get("history")
    return SenderLookup(history.sender if history else None)


def make_write_notes(model: TriageModel) -> Callable[[TriageState], Awaitable[TriageState]]:
    async def write_notes(state: TriageState) -> TriageState:
        """The model reads the email and its history and writes notes. It never sets status."""
        email_id = state["email"].id
        log.info("email %s write_notes: asking the model", email_id)
        started = time.perf_counter()
        lookup = _sender_lookup(state)
        try:
            async with asyncio.timeout(MODEL_DEADLINE):
                notes = await model.write_notes(
                    state["email"],
                    state["business_name"],
                    state["config"],
                    history=state.get("history"),
                    tools=[lookup],
                )
        # Any failure, not only ModelError: an uncaught one (a missing API key raises
        # TypeError) fails the whole run and leaves the email unread for good.
        except Exception as exc:
            return {
                "notes": None,
                "asked": asked("write_notes", lookup),
                "ai_failures": [_record_failure("write_notes", email_id, exc)],
            }
        log.info(
            "email %s write_notes: urgency=%s anger=%d sure=%s flags=%s asked=%s in %d ms",
            email_id,
            notes.urgency,
            notes.anger,
            notes.sure,
            _names(notes.risk_flags),
            lookup.calls,
            _ms(started),
        )
        return {"notes": notes, "asked": asked("write_notes", lookup)}

    return write_notes


def make_judge_rules(model: TriageModel) -> Callable[[TriageState], Awaitable[TriageState]]:
    async def judge_rules(state: TriageState) -> TriageState:
        """The model checks the email against the owner's plain-text rules. It runs beside
        write_notes, so it cannot see the notes. Mail that turns out not to be for the
        business is still judged; decide closes it before reading the verdicts."""
        config, email_id = state["config"], state["email"].id
        if not config.rules:
            log.info("email %s judge_rules: skipped (no rules)", email_id)
            return {"verdicts": []}
        started = time.perf_counter()
        lookup = _sender_lookup(state)
        try:
            async with asyncio.timeout(MODEL_DEADLINE):
                verdicts = await model.judge_rules(
                    state["email"],
                    state["business_name"],
                    config,
                    history=state.get("history"),
                    tools=[lookup],
                )
        except Exception as exc:
            # None, not []: an empty list means "no rule matched", and decide would route the
            # email as if the owner's rules had been read.
            return {
                "verdicts": None,
                "asked": asked("judge_rules", lookup),
                "ai_failures": [_record_failure("judge_rules", email_id, exc)],
            }
        log.info(
            "email %s judge_rules: %d rules, matched=%s asked=%s in %d ms",
            email_id,
            len(config.rules),
            _names(v.rule_id for v in verdicts if v.matched),
            lookup.calls,
            _ms(started),
        )
        return {"verdicts": verdicts, "asked": asked("judge_rules", lookup)}

    return judge_rules


def run_decide(state: TriageState) -> TriageState:
    """Plain Python: turns notes, word flags and rule verdicts into a route."""
    notes_failure = next(
        (f.kind for f in state.get("ai_failures", []) if f.call == "write_notes"), None
    )
    decision = decide(
        notes=state.get("notes"),
        word_flags=state.get("word_flags", set()),
        verdicts=state.get("verdicts", []),
        config=state["config"],
        sender=state["email"].sender,
        history=state.get("history"),
        in_spam=state["email"].in_spam,
        notes_failure=notes_failure,
    )
    # The reason is built from fixed strings and the owner's rule names, not the email.
    log.info(
        "email %s decide: route=%s urgency=%s reason=%r",
        state["email"].id,
        decision.route,
        decision.urgency,
        decision.reason,
    )
    return {"decision": decision}


def build_graph(model: TriageModel) -> CompiledStateGraph:
    graph = StateGraph(TriageState, context_schema=TriageContext)
    graph.add_node("word_check", run_word_check)
    graph.add_node("gather_context", gather_context)
    graph.add_node("write_notes", make_write_notes(model))
    graph.add_node("judge_rules", make_judge_rules(model))
    graph.add_node("decide", run_decide)
    graph.add_edge(START, "word_check")
    graph.add_edge(START, "gather_context")
    graph.add_edge("gather_context", "write_notes")
    graph.add_edge("gather_context", "judge_rules")
    graph.add_edge(["word_check", "write_notes", "judge_rules"], "decide")
    graph.add_edge("decide", END)
    return graph.compile()


async def triage(
    graph: CompiledStateGraph,
    email: Email,
    config: WorkspaceConfig,
    *,
    business_name: str,
    tools: Toolbox | None = None,
    callbacks: list[Any] | None = None,
) -> TriageState:
    # Callbacks go per run, not at compile time: one graph serves every tenant.
    run_config = {"callbacks": callbacks} if callbacks else None
    return await graph.ainvoke(
        {"email": email, "config": config, "business_name": business_name},
        config=run_config,
        context=TriageContext(tools=tools or Toolbox([])),
    )
