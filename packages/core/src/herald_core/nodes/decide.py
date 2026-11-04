"""Plain Python: turns notes, word flags and rule verdicts into a route. The rules live in
`herald_core.decide`; this file only adapts them to the graph state."""

import logging

from herald_core.decide import decide
from herald_core.state import TriageState

log = logging.getLogger(__name__)


def run_decide(state: TriageState) -> TriageState:
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
