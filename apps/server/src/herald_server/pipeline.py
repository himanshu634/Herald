"""Run one email through the triage graph and hand the result back to the API.

The pipeline never opens the database. It loads the email, runs the tools and saves the result
through `AgentApi`, and the API commits the result and publishes its events.
"""

import logging
import time

from langgraph.graph.state import CompiledStateGraph

from herald_core.graph import triage
from herald_core.history import EmailContext, History
from herald_core.schema import Decision, Email, Notes, WorkspaceConfig
from herald_server.internal.client import AgentApi
from herald_server.internal.schemas import TriageResult
from herald_server.tools import build_toolbox
from herald_server.tracing import NO_TRACING, Tracing, record_outcome

log = logging.getLogger(__name__)


async def _run(
    api: AgentApi,
    graph: CompiledStateGraph,
    email: Email,
    name: str,
    config: WorkspaceConfig,
    tracing: Tracing,
    trace_name: str,
    tag: str,
) -> tuple[Notes | None, Decision, EmailContext, int]:
    tools = build_toolbox(api, email.id)
    started = time.perf_counter()
    # The tracing never raises into triage: if it cannot open a trace, run.callbacks is empty.
    with tracing.run(
        trace_name,
        user_id=email.workspace_id,
        session_id=email.id,
        tags=[tag],
        metadata={"email_id": email.id},
    ) as run:
        state = await triage(
            graph, email, config, business_name=name, tools=tools, callbacks=run.callbacks
        )
        record_outcome(tracing, run, state["decision"], state.get("notes"))
    total_ms = round((time.perf_counter() - started) * 1000)
    # Copy the toolbox's list and dict so nothing that runs later can change what we save.
    context = EmailContext.from_run(
        state.get("history") or History(), list(tools.failed), dict(tools.ms) | {"triage": total_ms}
    )
    return state.get("notes"), state["decision"], context, total_ms


async def trial_read(
    api: AgentApi,
    graph: CompiledStateGraph,
    email_id: str,
    config: WorkspaceConfig,
    tracing: Tracing = NO_TRACING,
) -> tuple[Notes | None, Decision]:
    """What Herald would make of this email with a draft config. Writes and publishes nothing.

    The owner tries a fact or rule change on one email before keeping it, so this must leave
    the email, its events and the saved config exactly as they were. It only reads through
    the API and never calls the save route.
    """
    loaded = await api.triage_input(email_id)
    email = loaded.email
    notes, decision, _context, total_ms = await _run(
        api, graph, email, loaded.business_name, config, tracing, "trial-read", "try"
    )
    log.info(
        "email %s trial read in %d ms: route=%s rules=%s",
        email.id,
        total_ms,
        decision.route,
        ",".join(decision.fired_rule_ids) or "none",
    )
    return notes, decision


async def process_email(
    api: AgentApi, graph: CompiledStateGraph, email_id: str, tracing: Tracing = NO_TRACING
) -> Decision:
    loaded = await api.triage_input(email_id)
    email = loaded.email
    log.info("email %s triage started in workspace %s", email.id, email.workspace_id)
    notes, decision, context, total_ms = await _run(
        api, graph, email, loaded.business_name, loaded.config, tracing, "triage", "live"
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
        ",".join(context.failed) or "none",
    )
    await api.save_triage_result(
        email.id, TriageResult(notes=notes, decision=decision, context=context)
    )
    return decision
