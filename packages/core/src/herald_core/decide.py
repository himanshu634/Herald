"""The decide step: plain Python, no AI.

The AI suggests (notes, rule verdicts); this function decides. Order, first match wins:

1. Safety floor (from the AI or the word check) -> alert. The one exception: mail the provider
   filed as spam that the AI is also sure is not for the business goes to needs a look.
2. Not for the business (see `not_for_business`) -> closed.
3. The owner's rules; the most urgent result wins (alert > close). A set-urgency rule never
   lowers an urgent email. Without notes the verdicts are not used (see `decide`).
4. Urgent, or anger 5 -> alert.
5. Anger 4 from an important contact, about to cancel, or the third email about the same
   thing this week (see `repeat_count`) -> alert.
6. No notes, the owner's rules could not be checked, or the AI is unsure -> needs a look.
7. Spam or not for me -> closed.
8. Everything else -> inbox.
"""

from datetime import timedelta

from herald_core.history import History
from herald_core.schema import (
    FLOOR_FLAGS,
    SPAM_TOPIC,
    Decision,
    FailureKind,
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
    urgent or "cancel anytime" as a customer leaving. Rules are judged beside the notes, so
    such mail still gets verdicts; this check runs first and they are never read. An unsure
    verdict, or an important contact, takes the normal path: a customer email filed here by
    mistake would be closed unseen.
    """
    return (
        notes is not None
        and notes.sure
        and is_spam(notes.topic)
        and not config.is_important(sender)
    )


REPEAT_WINDOW = timedelta(days=7)
# This email plus two earlier ones: "a third email about the same thing".
REPEAT_ALERT_AT = 3
# Statuses that end a matter. A new email after the owner marked one done (or after clutter
# was closed) starts a new matter, so those do not count as repeats. Status is a plain string
# here: the server owns the status names.
_RESOLVED = frozenset({"done", "closed"})


def repeat_count(notes: Notes, history: History | None) -> int:
    """How many emails, this one included, the sender sent about this topic in the last week.

    Counted in code from Herald's own history, not judged by the AI: "about the same thing" is
    the same topic, and only emails not yet done or closed count. Sender history holds at most
    the 5 newest emails, which is enough to reach 3. With no `as_of` the window cannot be
    placed, so nothing counts: an alert must not rest on a guess.
    """
    sender = history.sender if history else None
    if sender is None or sender.as_of is None or is_spam(notes.topic):
        return 1
    since = sender.as_of - REPEAT_WINDOW
    topic = notes.topic.strip().casefold()
    earlier = [
        past
        for past in sender.recent
        if past.received_at >= since
        and past.status not in _RESOLVED
        and past.topic is not None
        and past.topic.strip().casefold() == topic
    ]
    return 1 + len(earlier)


def decide(
    *,
    notes: Notes | None,
    word_flags: set[RiskFlag],
    verdicts: list[RuleVerdict] | None,
    config: WorkspaceConfig,
    sender: str,
    history: History | None = None,
    in_spam: bool = False,
    notes_failure: FailureKind | None = None,
) -> Decision:
    """`verdicts` is None when the rules call failed; `notes_failure` says why the notes are
    missing, so the owner sees "unavailable" apart from "could not read"."""
    ai_flags = set(notes.risk_flags) if notes else set()
    floor = sorted((ai_flags | word_flags) & FLOOR_FLAGS)
    urgency = notes.urgency if notes else None

    # Phishing is full of floor words ("legal action", "chargeback"), so reading Spam would
    # alert on junk. Only when the provider AND the AI both call it spam does a floor hit drop
    # to needs a look: still shown, never closed. A real customer in Spam still alerts.
    if floor and in_spam and not_for_business(notes, config, sender):
        return Decision(
            route=Route.NEEDS_A_LOOK,
            urgency=urgency,
            reason="Safety floor in Spam: " + ", ".join(floor),
            floor_flags=floor,
        )

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

    # The rules are judged in parallel with the notes, so verdicts can arrive when the notes
    # failed. They are dropped: an email the AI could not read goes to needs a look, and only
    # the safety floor above may alert on it. A matched close rule must not hide it unseen.
    # A failed rules call is not "no rule matched": an owner's alert or close rule may have
    # fired. Without rules nothing was asked, so nothing is missing.
    rules_unread = verdicts is None and bool(config.rules)
    if notes is None or verdicts is None:
        verdicts = []
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
        if notes_failure in (FailureKind.UNAVAILABLE, FailureKind.SETUP):
            return route(Route.NEEDS_A_LOOK, "The AI was unavailable")
        return route(Route.NEEDS_A_LOOK, "The AI could not read this email")

    if urgency is Urgency.URGENT:
        return route(Route.ALERT, "Urgent")
    if notes.anger == 5:
        return route(Route.ALERT, "Extremely angry (anger 5)")
    if notes.anger == 4 and config.is_important(sender):
        return route(Route.ALERT, "Angry important contact")
    if RiskFlag.ABOUT_TO_CANCEL in ai_flags:
        return route(Route.ALERT, "Customer about to cancel")
    if repeat_count(notes, history) >= REPEAT_ALERT_AT:
        return route(Route.ALERT, "Third email about the same thing this week")

    # After the alerts above, which a rule can never quiet (alert beats close), and before
    # inbox and closed, which an unread rule might have changed.
    if rules_unread:
        return route(Route.NEEDS_A_LOOK, "Your rules could not be checked")
    if not notes.sure:
        return route(Route.NEEDS_A_LOOK, "The AI is unsure")
    if is_spam(notes.topic):
        return route(Route.CLOSED, SPAM_TOPIC)
    return route(Route.INBOX, "Routine")
