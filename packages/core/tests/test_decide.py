from datetime import datetime, timedelta

import pytest

from herald_core.decide import decide, not_for_business
from herald_core.history import History, PastEmail, SenderHistory
from herald_core.schema import (
    SPAM_TOPIC,
    Notes,
    RiskFlag,
    Route,
    Rule,
    RuleAction,
    RuleVerdict,
    Urgency,
    WorkspaceConfig,
)

CLOSE_ALL = Rule(id="r-close", name="Close everything", when="any email", action=RuleAction.CLOSE)
ALERT_TRAVEL = Rule(
    id="r-travel", name="Travelling soon", when="trip in 48 hours", action=RuleAction.ALERT
)
SET_HIGH = Rule(
    id="r-damaged",
    name="Damaged bag",
    when="the bag arrived damaged",
    action=RuleAction.SET_URGENCY,
    urgency=Urgency.HIGH,
)
SET_LOW = Rule(
    id="r-ideas",
    name="Ideas",
    when="a product idea",
    action=RuleAction.SET_URGENCY,
    urgency=Urgency.LOW,
)
CONFIG = WorkspaceConfig(
    business_profile="Online luggage brand.",
    topics=["Orders and delivery", "Damaged or defective"],
    important_contacts=["bigcorp.com"],
    rules=[CLOSE_ALL, ALERT_TRAVEL, SET_HIGH, SET_LOW],
)


def notes(**overrides) -> Notes:
    base = {
        "topic": "Orders and delivery",
        "urgency": Urgency.NORMAL,
        "anger": 1,
        "summary": "Where is my order?",
        "sure": True,
    }
    return Notes(**base | overrides)


def run(
    n,
    *,
    word_flags=frozenset(),
    matched=(),
    sender="a@customer.in",
    history=None,
    in_spam=False,
):
    verdicts = [RuleVerdict(rule_id=r, matched=True) for r in matched]
    return decide(
        notes=n,
        word_flags=set(word_flags),
        verdicts=verdicts,
        config=CONFIG,
        sender=sender,
        history=history,
        in_spam=in_spam,
    )


NOW = datetime(2026, 11, 4, 12, 0)


def earlier(days_ago, topic="Orders and delivery", status="inbox"):
    return PastEmail(
        id=f"e-{days_ago}-{topic}-{status}",
        received_at=NOW - timedelta(days=days_ago),
        subject="Where is my order?",
        topic=topic,
        urgency=Urgency.NORMAL,
        status=status,
        summary=None,
    )


def sender_history(*recent, as_of=NOW):
    return History(
        sender=SenderHistory(
            first_seen=NOW - timedelta(days=20),
            count_7d=len(recent),
            count_30d=len(recent),
            top_topics=[],
            recent=list(recent),
            as_of=as_of,
        )
    )


def test_routine_email_goes_to_inbox():
    assert run(notes()).route is Route.INBOX


@pytest.mark.parametrize("source", ["ai", "word_check"])
def test_safety_floor_beats_a_close_rule(source):
    ai_flags = [RiskFlag.ACCOUNT_OR_DATA] if source == "ai" else []
    words = {RiskFlag.ACCOUNT_OR_DATA} if source == "word_check" else set()
    decision = run(notes(risk_flags=ai_flags), word_flags=words, matched=["r-close"])
    assert decision.route is Route.ALERT
    assert decision.floor_flags == [RiskFlag.ACCOUNT_OR_DATA]


def test_floor_alerts_even_when_the_ai_failed():
    decision = run(None, word_flags={RiskFlag.LEGAL_THREAT})
    assert decision.route is Route.ALERT


def test_alert_rule_beats_close_rule():
    decision = run(notes(), matched=["r-close", "r-travel"])
    assert decision.route is Route.ALERT
    assert decision.reason == "Rule: Travelling soon"


def test_close_rule_can_quiet_an_angry_email():
    assert run(notes(anger=5), matched=["r-close"]).route is Route.CLOSED


def test_calm_but_urgent_alerts():
    assert run(notes(urgency=Urgency.URGENT)).route is Route.ALERT


def test_set_urgency_rule_raises_urgency():
    decision = run(notes(urgency=Urgency.NORMAL), matched=["r-damaged"])
    assert (decision.route, decision.urgency) == (Route.INBOX, Urgency.HIGH)


def test_set_urgency_rule_can_lower_urgency():
    decision = run(notes(urgency=Urgency.HIGH), matched=["r-ideas"])
    assert (decision.route, decision.urgency) == (Route.INBOX, Urgency.LOW)


@pytest.mark.parametrize("rule_id", ["r-damaged", "r-ideas"])
def test_set_urgency_rule_never_lowers_an_urgent_email(rule_id):
    # A bag that breaks at the airport is "urgent" to the AI; the owner's "damaged -> high"
    # rule must not turn that alert into an inbox email.
    decision = run(notes(urgency=Urgency.URGENT), matched=[rule_id])
    assert decision.route is Route.ALERT
    assert decision.urgency is Urgency.URGENT
    assert decision.fired_rule_ids == [rule_id]


@pytest.mark.parametrize("matched", [["r-damaged", "r-ideas"], ["r-ideas", "r-damaged"]])
def test_most_urgent_set_urgency_rule_wins(matched):
    assert run(notes(), matched=matched).urgency is Urgency.HIGH


def test_anger_five_alerts():
    assert run(notes(anger=5)).route is Route.ALERT


def test_anger_four_alerts_only_for_important_contacts():
    assert run(notes(anger=4)).route is Route.INBOX
    assert run(notes(anger=4), sender="hr@bigcorp.com").route is Route.ALERT


def test_about_to_cancel_alerts():
    assert run(notes(risk_flags=[RiskFlag.ABOUT_TO_CANCEL])).route is Route.ALERT


def test_no_notes_or_unsure_needs_a_look():
    assert run(None).route is Route.NEEDS_A_LOOK
    assert run(notes(sure=False)).route is Route.NEEDS_A_LOOK


def test_spam_is_closed():
    assert run(notes(topic=SPAM_TOPIC)).route is Route.CLOSED


@pytest.mark.parametrize(
    ("overrides", "matched"),
    [
        ({}, ["r-travel"]),  # an alert rule fired on a newsletter
        ({"urgency": Urgency.URGENT}, []),  # "sale ends today"
        ({"anger": 5}, []),  # SALE IS LIVE in capitals
        ({"risk_flags": [RiskFlag.ABOUT_TO_CANCEL]}, []),  # "cancel anytime"
    ],
)
def test_sure_spam_closes_before_rules_and_defaults(overrides, matched):
    decision = run(notes(topic=SPAM_TOPIC, **overrides), matched=matched)
    assert decision.route is Route.CLOSED
    assert decision.reason == SPAM_TOPIC
    assert decision.fired_rule_ids == []


def test_spam_topic_matches_loosely():
    assert run(notes(topic=" spam OR not for me "), matched=["r-travel"]).route is Route.CLOSED


def test_safety_floor_still_alerts_on_spam():
    decision = run(notes(topic=SPAM_TOPIC), word_flags={RiskFlag.LEGAL_THREAT})
    assert decision.route is Route.ALERT


def test_floor_word_in_spam_mail_the_ai_calls_spam_needs_a_look():
    # Phishing in Gmail's Spam folder: both Gmail and the AI say spam, so no alert.
    decision = run(notes(topic=SPAM_TOPIC), word_flags={RiskFlag.LEGAL_THREAT}, in_spam=True)
    assert decision.route is Route.NEEDS_A_LOOK
    assert decision.floor_flags == [RiskFlag.LEGAL_THREAT]


@pytest.mark.parametrize(
    "n",
    [
        notes(),  # a real customer Gmail filed as spam
        notes(topic=SPAM_TOPIC, sure=False),
        None,  # the AI failed
    ],
)
def test_floor_word_in_spam_mail_still_alerts_unless_the_ai_is_sure_it_is_spam(n):
    decision = run(n, word_flags={RiskFlag.LEGAL_THREAT}, in_spam=True)
    assert decision.route is Route.ALERT


def test_floor_word_in_spam_mail_from_an_important_contact_alerts():
    decision = run(
        notes(topic=SPAM_TOPIC),
        word_flags={RiskFlag.LEGAL_THREAT},
        sender="ceo@bigcorp.com",
        in_spam=True,
    )
    assert decision.route is Route.ALERT


def test_unsure_spam_takes_the_normal_path():
    assert run(notes(topic=SPAM_TOPIC, sure=False)).route is Route.NEEDS_A_LOOK
    assert run(notes(topic=SPAM_TOPIC, sure=False), matched=["r-travel"]).route is Route.ALERT


def test_spam_from_an_important_contact_takes_the_normal_path():
    sender = "hr@bigcorp.com"
    assert run(notes(topic=SPAM_TOPIC), matched=["r-travel"], sender=sender).route is Route.ALERT
    assert run(notes(topic=SPAM_TOPIC), sender=sender).route is Route.CLOSED


def test_not_for_business_needs_notes():
    assert not not_for_business(None, CONFIG, "a@customer.in")


def test_notes_have_no_status_field():
    assert "status" not in Notes.model_fields


def test_third_email_about_the_same_thing_alerts():
    decision = run(notes(), history=sender_history(earlier(1), earlier(5)))
    assert decision.route is Route.ALERT
    assert decision.reason == "Third email about the same thing this week"


def test_second_email_about_the_same_thing_does_not_alert():
    assert run(notes(), history=sender_history(earlier(1))).route is Route.INBOX


@pytest.mark.parametrize(
    "recent",
    [
        # Older than a week.
        (earlier(1), earlier(9)),
        # About something else.
        (earlier(1), earlier(2, topic="Damaged or defective")),
        # The owner finished it, or it was clutter: a new email starts a new matter.
        (earlier(1), earlier(2, status="done")),
        (earlier(1), earlier(2, status="closed")),
    ],
)
def test_repeats_that_are_old_other_or_resolved_do_not_count(recent):
    assert run(notes(), history=sender_history(*recent)).route is Route.INBOX


def test_topic_match_ignores_case():
    history = sender_history(earlier(1, topic="orders and delivery"), earlier(2))
    assert run(notes(), history=history).route is Route.ALERT


def test_repeats_need_the_time_of_the_email():
    # History from before `as_of` existed cannot be windowed, so it never alerts on its own.
    history = sender_history(earlier(1), earlier(2), as_of=None)
    assert run(notes(), history=history).route is Route.INBOX


def test_repeat_contact_beats_unsure():
    history = sender_history(earlier(1), earlier(2))
    assert run(notes(sure=False), history=history).route is Route.ALERT
