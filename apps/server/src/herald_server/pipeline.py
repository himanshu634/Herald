"""Run one email through the triage graph and hand the result back to the API.

The pipeline never opens the database. It loads the email, runs the tools and saves the result
through `AgentApi`, and the API commits the result and publishes its events.
"""

import logging
import time

from langgraph.graph.state import CompiledStateGraph

from herald_core.graph import triage
from herald_core.history import EmailContext, History
from herald_core.schema import Decision
from herald_server.internal.client import AgentApi
from herald_server.internal.schemas import TriageResult
from herald_server.tools import build_toolbox

log = logging.getLogger(__name__)


async def process_email(api: AgentApi, graph: CompiledStateGraph, email_id: str) -> Decision:
    loaded = await api.triage_input(email_id)
    email = loaded.email
    tools = build_toolbox(api, email.id)
    log.info("email %s triage started in workspace %s", email.id, email.workspace_id)
    started = time.perf_counter()
    state = await triage(
        graph, email, loaded.config, business_name=loaded.business_name, tools=tools
    )
    total_ms = round((time.perf_counter() - started) * 1000)
    notes, decision = state.get("notes"), state["decision"]
    # Copy the toolbox's list and dict so nothing that runs later can change what we save.
    context = EmailContext.from_run(
        state.get("history") or History(), list(tools.failed), dict(tools.ms) | {"triage": total_ms}
    )
    log.info(
        "email %s triaged in %d ms: route=%s urgency=%s rules=%s floor=%s notes=%s failed tools=%s",
        email.id,
        total_ms,
        decision.route,
        decision.urgency,
        ",".join(decision.fired_rule_ids) or "none",
        ",".join(decision.floor_flags) or "none",
        "yes" if notes else "no",
        ",".join(tools.failed) or "none",
    )
    await api.save_triage_result(
        email.id, TriageResult(notes=notes, decision=decision, context=context)
    )
    return decision
