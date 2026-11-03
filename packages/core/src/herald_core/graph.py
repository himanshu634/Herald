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
from dataclasses import dataclass
from typing import TypedDict

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
from herald_core.model import ModelError, TriageModel
from herald_core.safety import word_check
from herald_core.schema import Decision, Email, Notes, RiskFlag, RuleVerdict, WorkspaceConfig
from herald_core.tools import Toolbox


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
    notes_error: str | None
    verdicts: list[RuleVerdict]
    decision: Decision


def build_graph(model: TriageModel) -> CompiledStateGraph:
    def run_word_check(state: TriageState) -> TriageState:
        email = state["email"]
        return {"word_flags": word_check(f"{email.subject}\n{email.body}")}

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
        return {"history": History(sender=sender, thread=thread, corrections=corrections)}

    async def write_notes(state: TriageState) -> TriageState:
        try:
            return {
                "notes": await model.write_notes(
                    state["email"],
                    state["business_name"],
                    state["config"],
                    history=state.get("history"),
                )
            }
        except ModelError as exc:
            return {"notes": None, "notes_error": str(exc)}

    async def judge_rules(state: TriageState) -> TriageState:
        config = state["config"]
        if not config.rules or state.get("notes") is None:
            return {"verdicts": []}
        try:
            verdicts = await model.judge_rules(
                state["email"], state["business_name"], config, history=state.get("history")
            )
            return {"verdicts": verdicts}
        except ModelError:
            return {"verdicts": []}

    def run_decide(state: TriageState) -> TriageState:
        return {
            "decision": decide(
                notes=state.get("notes"),
                word_flags=state.get("word_flags", set()),
                verdicts=state.get("verdicts", []),
                config=state["config"],
                sender=state["email"].sender,
            )
        }

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
