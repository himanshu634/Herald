"""The model reads the email and its history and writes notes. It never sets status.

It may call sender_history first, when it decides it needs the sender's earlier emails.
"""

import logging
import time
from collections.abc import Awaitable, Callable

from herald_core.model import TriageModel
from herald_core.model_tools import SenderLookup, asked
from herald_core.nodes.log_names import names
from herald_core.state import TriageState

log = logging.getLogger(__name__)


def make_write_notes(model: TriageModel) -> Callable[[TriageState], Awaitable[TriageState]]:
    async def write_notes(state: TriageState) -> TriageState:
        email_id = state["email"].id
        log.info("email %s write_notes: asking the model", email_id)
        started = time.perf_counter()
        history = state.get("history")
        lookup = SenderLookup(history.sender if history else None)
        try:
            notes = await model.write_notes(
                state["email"],
                state["business_name"],
                state["config"],
                history=history,
                tools=[lookup],
            )
        # Any failure, not only ModelError: an uncaught one (a missing API key raises
        # TypeError) fails the whole run and leaves the email unread for good.
        except Exception:
            log.exception("write_notes failed for email %s", email_id)
            return {"notes": None, "asked": asked("write_notes", lookup)}
        log.info(
            "email %s write_notes: urgency=%s anger=%d sure=%s flags=%s asked=%s in %d ms",
            email_id,
            notes.urgency,
            notes.anger,
            notes.sure,
            names(notes.risk_flags),
            lookup.calls,
            round((time.perf_counter() - started) * 1000),
        )
        return {"notes": notes, "asked": asked("write_notes", lookup)}

    return write_notes
