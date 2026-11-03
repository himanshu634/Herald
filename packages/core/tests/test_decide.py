import pytest

from herald_core.decide import decide
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
CONFIG = WorkspaceConfig(
    business_profile="Online luggage brand.",
    topics=["Orders and delivery", "Damaged or defective"],
    important_contacts=["bigcorp.com"],
    rules=[CLOSE_ALL, ALERT_TRAVEL],
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


def run(n, *, word_flags=frozenset(), matched=(), sender="a@customer.in"):
    verdicts = [RuleVerdict(rule_id=r, matched=True) for r in matched]
    return decide(
        notes=n, word_flags=set(word_flags), verdicts=verdicts, config=CONFIG, sender=sender
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


def test_notes_have_no_status_field():
    assert "status" not in Notes.model_fields
