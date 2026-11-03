"""The decide step: plain Python, no AI.

The AI suggests (notes, rule verdicts); this function decides. Order, first match wins:

1. Safety floor (from the AI or the word check) -> alert, always.
2. The owner's rules; the most urgent result wins (alert > close).
3. Urgent, or anger 5 -> alert.
4. Anger 4 from an important contact, or about to cancel -> alert.
5. No notes, or the AI is unsure -> needs a look.
6. Spam or not for me -> closed.
7. Everything else -> inbox.
"""

from herald_core.schema import (
    FLOOR_FLAGS,
    SPAM_TOPIC,
    Decision,
    Notes,
    RiskFlag,
    Route,
    RuleAction,
    RuleVerdict,
    Urgency,
    WorkspaceConfig,
)


def decide(
    *,
    notes: Notes | None,
    word_flags: set[RiskFlag],
    verdicts: list[RuleVerdict],
    config: WorkspaceConfig,
    sender: str,
) -> Decision:
    ai_flags = set(notes.risk_flags) if notes else set()
    floor = sorted((ai_flags | word_flags) & FLOOR_FLAGS)
    urgency = notes.urgency if notes else None

    if floor:
        return Decision(
            route=Route.ALERT,
            urgency=Urgency.URGENT,
            reason="Safety floor: " + ", ".join(floor),
            floor_flags=floor,
        )

    rules_by_id = {r.id: r for r in config.rules}
    fired = [rules_by_id[v.rule_id] for v in verdicts if v.matched and v.rule_id in rules_by_id]
    fired_ids = [r.id for r in fired]

    for rule in fired:
        if rule.action is RuleAction.SET_URGENCY and rule.urgency is not None:
            urgency = rule.urgency

    alerting = [r for r in fired if r.action is RuleAction.ALERT]
    if alerting:
        return Decision(
            route=Route.ALERT,
            urgency=urgency,
            reason=f"Rule: {alerting[0].name}",
            fired_rule_ids=fired_ids,
        )
    closing = [r for r in fired if r.action is RuleAction.CLOSE]
    if closing:
        return Decision(
            route=Route.CLOSED,
            urgency=urgency,
            reason=f"Rule: {closing[0].name}",
            fired_rule_ids=fired_ids,
        )

    if notes is None:
        return Decision(
            route=Route.NEEDS_A_LOOK,
            urgency=urgency,
            reason="The AI could not read this email",
            fired_rule_ids=fired_ids,
        )

    if urgency is Urgency.URGENT or notes.anger == 5:
        reason = "Urgent" if urgency is Urgency.URGENT else "Extremely angry (anger 5)"
        return Decision(route=Route.ALERT, urgency=urgency, reason=reason, fired_rule_ids=fired_ids)

    if notes.anger == 4 and config.is_important(sender):
        return Decision(
            route=Route.ALERT,
            urgency=urgency,
            reason="Angry important contact",
            fired_rule_ids=fired_ids,
        )
    if RiskFlag.ABOUT_TO_CANCEL in ai_flags:
        return Decision(
            route=Route.ALERT,
            urgency=urgency,
            reason="Customer about to cancel",
            fired_rule_ids=fired_ids,
        )

    if not notes.sure:
        return Decision(
            route=Route.NEEDS_A_LOOK,
            urgency=urgency,
            reason="The AI is unsure",
            fired_rule_ids=fired_ids,
        )
    if notes.topic == SPAM_TOPIC:
        return Decision(
            route=Route.CLOSED, urgency=urgency, reason=SPAM_TOPIC, fired_rule_ids=fired_ids
        )
    return Decision(route=Route.INBOX, urgency=urgency, reason="Routine", fired_rule_ids=fired_ids)
