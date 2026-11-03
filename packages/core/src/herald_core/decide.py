"""The decide step: plain Python, no AI.

The AI suggests (notes, rule verdicts); this function decides. Order, first match wins:

1. Safety floor (from the AI or the word check) -> alert, always.
2. Not for the business (see `not_for_business`) -> closed.
3. The owner's rules; the most urgent result wins (alert > close). A set-urgency rule never
   lowers an urgent email.
4. Urgent, or anger 5 -> alert.
5. Anger 4 from an important contact, or about to cancel -> alert.
6. No notes, or the AI is unsure -> needs a look.
7. Spam or not for me -> closed.
8. Everything else -> inbox.
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

_URGENCY_ORDER = [Urgency.LOW, Urgency.NORMAL, Urgency.HIGH, Urgency.URGENT]


def is_spam(topic: str) -> bool:
    # Notes.topic is free text from the model, so match it loosely.
    return topic.strip().casefold() == SPAM_TOPIC.casefold()


def not_for_business(notes: Notes | None, config: WorkspaceConfig, sender: str) -> bool:
    """True when the AI is sure the email is not about this business at all.

    Such mail (promotions, newsletters, app notifications) closes before the owner's rules
    and the urgent / anger / cancel defaults, which would otherwise read "sale ends today" as
    urgent or "cancel anytime" as a customer leaving. The graph uses the same check to skip
    judging rules, so the two must not drift. An unsure verdict, or an important contact,
    takes the normal path: a customer email filed here by mistake would be closed unseen.
    """
    return (
        notes is not None
        and notes.sure
        and is_spam(notes.topic)
        and not config.is_important(sender)
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

    # After the floor on purpose: a threat is never closed, whatever the AI files it under.
    if not_for_business(notes, config, sender):
        return Decision(route=Route.CLOSED, urgency=urgency, reason=SPAM_TOPIC)

    rules_by_id = {r.id: r for r in config.rules}
    fired = [rules_by_id[v.rule_id] for v in verdicts if v.matched and v.rule_id in rules_by_id]
    fired_ids = [r.id for r in fired]

    # Set-urgency rules: the most urgent one wins, as with every rule. A rule may lower the
    # AI's urgency for sorting, but never below "urgent": that would turn an alert into an
    # inbox email (a "damaged -> high" rule burying a bag that broke at the airport). To quiet
    # an urgent email the owner writes a close rule, which says so.
    levels = [r.urgency for r in fired if r.action is RuleAction.SET_URGENCY and r.urgency]
    if levels and urgency is not Urgency.URGENT:
        urgency = max(levels, key=_URGENCY_ORDER.index)

    def route(to: Route, reason: str) -> Decision:
        return Decision(route=to, urgency=urgency, reason=reason, fired_rule_ids=fired_ids)

    # Alert rules are checked before close rules, so the more urgent result wins.
    for action, to in ((RuleAction.ALERT, Route.ALERT), (RuleAction.CLOSE, Route.CLOSED)):
        rule = next((r for r in fired if r.action is action), None)
        if rule is not None:
            return route(to, f"Rule: {rule.name}")

    if notes is None:
        return route(Route.NEEDS_A_LOOK, "The AI could not read this email")

    if urgency is Urgency.URGENT:
        return route(Route.ALERT, "Urgent")
    if notes.anger == 5:
        return route(Route.ALERT, "Extremely angry (anger 5)")
    if notes.anger == 4 and config.is_important(sender):
        return route(Route.ALERT, "Angry important contact")
    if RiskFlag.ABOUT_TO_CANCEL in ai_flags:
        return route(Route.ALERT, "Customer about to cancel")

    if not notes.sure:
        return route(Route.NEEDS_A_LOOK, "The AI is unsure")
    if is_spam(notes.topic):
        return route(Route.CLOSED, SPAM_TOPIC)
    return route(Route.INBOX, "Routine")
