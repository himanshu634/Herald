"""Runs the history tools in code, no AI, before the model reads the email."""

import asyncio
import logging

from langgraph.runtime import Runtime

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
from herald_core.state import TriageContext, TriageState

log = logging.getLogger(__name__)


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
