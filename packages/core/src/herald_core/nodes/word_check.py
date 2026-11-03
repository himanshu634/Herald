"""The safety floor: a regex word check that starts from START and never waits on tools or AI."""

import logging

from herald_core.nodes.log_names import names
from herald_core.safety import word_check
from herald_core.state import TriageState

log = logging.getLogger(__name__)


def run_word_check(state: TriageState) -> TriageState:
    email = state["email"]
    flags = word_check(f"{email.subject}\n{email.body}")
    log.info("email %s word_check: flags=%s", email.id, names(flags))
    return {"word_flags": flags}
