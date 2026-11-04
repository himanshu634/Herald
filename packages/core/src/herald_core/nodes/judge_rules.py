"""The model checks the email against the owner's plain-text rules."""

import logging
import time
from collections.abc import Awaitable, Callable

from herald_core.decide import not_for_business
from herald_core.model import TriageModel
from herald_core.model_tools import SenderLookup, asked
from herald_core.nodes.log_names import names
from herald_core.state import TriageState

log = logging.getLogger(__name__)


def make_judge_rules(model: TriageModel) -> Callable[[TriageState], Awaitable[TriageState]]:
    async def judge_rules(state: TriageState) -> TriageState:
        config, notes, email_id = state["config"], state.get("notes"), state["email"].id
        # Mail that decide will close before the rules needs no verdicts: skip the model call.
        if not config.rules:
            skip = "no rules"
        elif notes is None:
            skip = "no notes"
        elif not_for_business(notes, config, state["email"].sender):
            skip = "not for the business"
        else:
            skip = None
        if skip:
            log.info("email %s judge_rules: skipped (%s)", email_id, skip)
            return {"verdicts": []}
        started = time.perf_counter()
        history = state.get("history")
        lookup = SenderLookup(history.sender if history else None)
        # write_notes ran first and wrote its own lookups: add to them, not over them.
        before = state.get("asked", [])
        try:
            verdicts = await model.judge_rules(
                state["email"], state["business_name"], config, history=history, tools=[lookup]
            )
        except Exception:
            log.exception("judge_rules failed for email %s", email_id)
            return {"verdicts": [], "asked": before + asked("judge_rules", lookup)}
        log.info(
            "email %s judge_rules: %d rules, matched=%s asked=%s in %d ms",
            email_id,
            len(config.rules),
            names(v.rule_id for v in verdicts if v.matched),
            lookup.calls,
            round((time.perf_counter() - started) * 1000),
        )
        return {"verdicts": verdicts, "asked": before + asked("judge_rules", lookup)}

    return judge_rules
