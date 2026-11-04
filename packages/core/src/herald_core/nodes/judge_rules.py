"""The model checks the email against the owner's plain-text rules.

It runs beside write_notes, so it cannot see the notes. Mail that turns out not to be for the
business is still judged; decide closes it before reading the verdicts.
"""

import logging
import time
from collections.abc import Awaitable, Callable

from herald_core.model import TriageModel
from herald_core.model_tools import SenderLookup, asked
from herald_core.nodes.log_names import names
from herald_core.state import TriageState

log = logging.getLogger(__name__)


def make_judge_rules(model: TriageModel) -> Callable[[TriageState], Awaitable[TriageState]]:
    async def judge_rules(state: TriageState) -> TriageState:
        config, email_id = state["config"], state["email"].id
        if not config.rules:
            log.info("email %s judge_rules: skipped (no rules)", email_id)
            return {"verdicts": []}
        started = time.perf_counter()
        history = state.get("history")
        lookup = SenderLookup(history.sender if history else None)
        try:
            verdicts = await model.judge_rules(
                state["email"], state["business_name"], config, history=history, tools=[lookup]
            )
        except Exception:
            log.exception("judge_rules failed for email %s", email_id)
            return {"verdicts": [], "asked": asked("judge_rules", lookup)}
        log.info(
            "email %s judge_rules: %d rules, matched=%s asked=%s in %d ms",
            email_id,
            len(config.rules),
            names(v.rule_id for v in verdicts if v.matched),
            lookup.calls,
            round((time.perf_counter() - started) * 1000),
        )
        return {"verdicts": verdicts, "asked": asked("judge_rules", lookup)}

    return judge_rules
