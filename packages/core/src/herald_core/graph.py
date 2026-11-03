"""The triage pipeline as a LangGraph graph.

    START -> word_check ─┐
    START -> write_notes ┴-> judge_rules -> decide -> END

The graph is compiled once and shared by every tenant; each run carries its workspace's
config in the state. Parallel nodes write different state keys.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from herald_core.decide import decide
from herald_core.model import ModelError, TriageModel
from herald_core.safety import word_check
from herald_core.schema import Decision, Email, Notes, RiskFlag, RuleVerdict, WorkspaceConfig


class TriageState(TypedDict, total=False):
    email: Email
    config: WorkspaceConfig
    word_flags: set[RiskFlag]
    notes: Notes | None
    notes_error: str | None
    verdicts: list[RuleVerdict]
    decision: Decision


def build_graph(model: TriageModel) -> CompiledStateGraph:
    def run_word_check(state: TriageState) -> TriageState:
        email = state["email"]
        return {"word_flags": word_check(f"{email.subject}\n{email.body}")}

    async def write_notes(state: TriageState) -> TriageState:
        try:
            return {"notes": await model.write_notes(state["email"], state["config"])}
        except ModelError as exc:
            return {"notes": None, "notes_error": str(exc)}

    async def judge_rules(state: TriageState) -> TriageState:
        rules = state["config"].rules
        if not rules or state.get("notes") is None:
            return {"verdicts": []}
        try:
            return {"verdicts": await model.judge_rules(state["email"], state["notes"], rules)}
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

    graph = StateGraph(TriageState)
    graph.add_node("word_check", run_word_check)
    graph.add_node("write_notes", write_notes)
    graph.add_node("judge_rules", judge_rules)
    graph.add_node("decide", run_decide)
    graph.add_edge(START, "word_check")
    graph.add_edge(START, "write_notes")
    graph.add_edge(["word_check", "write_notes"], "judge_rules")
    graph.add_edge("judge_rules", "decide")
    graph.add_edge("decide", END)
    return graph.compile()


async def triage(graph: CompiledStateGraph, email: Email, config: WorkspaceConfig) -> TriageState:
    return await graph.ainvoke({"email": email, "config": config})
