"""The triage pipeline as a LangGraph graph.

    START -> word_check ───────────────────┐
    START -> gather_context -> write_notes ┴-> judge_rules -> decide -> END

The graph is compiled once and shared by every tenant; each run carries its workspace's
config in the state and its toolbox in the runtime context. `gather_context` runs the history
tools in code before the model reads the email. `word_check` starts from START and never waits
on tools; `write_notes` waits on `gather_context`, so a slow tool can delay the alert by at
most the tool timeout (2 s). Parallel nodes write different state keys.

Each node lives in its own file in `nodes/`; this file only wires them together.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from herald_core.model import TriageModel
from herald_core.nodes.decide import run_decide
from herald_core.nodes.gather_context import gather_context
from herald_core.nodes.judge_rules import make_judge_rules
from herald_core.nodes.word_check import run_word_check
from herald_core.nodes.write_notes import make_write_notes
from herald_core.schema import Email, WorkspaceConfig
from herald_core.state import TriageContext, TriageState
from herald_core.tools import Toolbox


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
