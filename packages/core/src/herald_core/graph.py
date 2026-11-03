"""The triage pipeline as a LangGraph graph.

    START -> word_check ───────────────────┐
    START -> gather_context -> write_notes ┴-> judge_rules -> decide -> END

The graph is compiled once and shared by every tenant; each run carries its workspace's
config in the state and its toolbox in the runtime context. `gather_context` runs the history
tools in code before the model reads the email. `word_check` starts from START and never waits
on tools; `write_notes` waits on `gather_context`, so a slow tool can delay the alert by at
most the tool timeout (2 s). Parallel nodes write different state keys.
"""

import asyncio
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from herald_core.decide import decide, not_for_business
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
from herald_core.model import TriageModel
from herald_core.safety import word_check
from herald_core.schema import Decision, Email, Notes, RiskFlag, RuleVerdict, WorkspaceConfig
from herald_core.tools import Toolbox

# Each node logs one line keyed by email id, so runs of parallel emails can be told apart.
# Only ids, enums, counts and timings: never the sender, subject, body or the model's free text.
log = logging.getLogger(__name__)


def _names(items: Iterable[str]) -> str:
    return ",".join(sorted(items)) or "none"


@dataclass
class TriageContext:
    """Per-run objects that are not state: the toolbox is bound to one workspace by the server."""

    tools: Toolbox


class TriageState(TypedDict, total=False):
    email: Email
    config: WorkspaceConfig
    business_name: str
    word_flags: set[RiskFlag]
    history: History
    notes: Notes | None
    verdicts: list[RuleVerdict]
    decision: Decision


def build_graph(model: TriageModel) -> CompiledStateGraph:
    def run_word_check(state: TriageState) -> TriageState:
        email = state["email"]
        flags = word_check(f"{email.subject}\n{email.body}")
        log.info("email %s word_check: flags=%s", email.id, _names(flags))
        return {"word_flags": flags}

    async def gather_context(state: TriageState, runtime: Runtime[TriageContext]) -> TriageState:
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

    async def write_notes(state: TriageState) -> TriageState:
        email_id = state["email"].id
        log.info("email %s write_notes: asking the model", email_id)
        started = time.perf_counter()
        try:
            notes = await model.write_notes(
                state["email"],
                state["business_name"],
                state["config"],
                history=state.get("history"),
            )
        # Any failure, not only ModelError: an uncaught one (a missing API key raises
        # TypeError) fails the whole run and leaves the email unread for good.
        except Exception:
            log.exception("write_notes failed for email %s", email_id)
            return {"notes": None}
        log.info(
            "email %s write_notes: urgency=%s anger=%d sure=%s flags=%s in %d ms",
            email_id,
            notes.urgency,
            notes.anger,
            notes.sure,
            _names(notes.risk_flags),
            round((time.perf_counter() - started) * 1000),
        )
        return {"notes": notes}

    async def judge_rules(state: TriageState) -> TriageState:
        config, notes, email_id = state["config"], state.get("notes"), state["email"].id
        # Mail that decide will close before the rules needs no verdicts: skip the model call.
        if not config.rules:
            skip = "no rules"
        elif notes is None:
            skip = "no notes"
        elif not_for_business(notes, config, state["email"].sender):
            skip = "not for the business"
        else:
            skip = None
        if skip:
            log.info("email %s judge_rules: skipped (%s)", email_id, skip)
            return {"verdicts": []}
        started = time.perf_counter()
        try:
            verdicts = await model.judge_rules(
                state["email"], state["business_name"], config, history=state.get("history")
            )
        except Exception:
            log.exception("judge_rules failed for email %s", email_id)
            return {"verdicts": []}
        log.info(
            "email %s judge_rules: %d rules, matched=%s in %d ms",
            email_id,
            len(config.rules),
            _names(v.rule_id for v in verdicts if v.matched),
            round((time.perf_counter() - started) * 1000),
        )
        return {"verdicts": verdicts}

    def run_decide(state: TriageState) -> TriageState:
        decision = decide(
            notes=state.get("notes"),
            word_flags=state.get("word_flags", set()),
            verdicts=state.get("verdicts", []),
            config=state["config"],
            sender=state["email"].sender,
            history=state.get("history"),
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

    graph = StateGraph(TriageState, context_schema=TriageContext)
    graph.add_node("word_check", run_word_check)
    graph.add_node("gather_context", gather_context)
    graph.add_node("write_notes", write_notes)
    graph.add_node("judge_rules", judge_rules)
    graph.add_node("decide", run_decide)
    graph.add_edge(START, "word_check")
    graph.add_edge(START, "gather_context")
    graph.add_edge("gather_context", "write_notes")
    graph.add_edge(["word_check", "write_notes"], "judge_rules")
    graph.add_edge("judge_rules", "decide")
    graph.add_edge("decide", END)
    return graph.compile()


async def triage(
    graph: CompiledStateGraph,
    email: Email,
    config: WorkspaceConfig,
    *,
    business_name: str,
    tools: Toolbox | None = None,
) -> TriageState:
    return await graph.ainvoke(
        {"email": email, "config": config, "business_name": business_name},
        context=TriageContext(tools=tools or Toolbox([])),
    )
