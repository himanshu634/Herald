from types import SimpleNamespace

from herald_core.history import CorrectionExample, Corrections, History
from herald_core.model import AnthropicModel, _Verdicts
from herald_core.prompt import email_block, history_block, system_prompt
from herald_core.schema import Email, Notes, Rule, RuleAction, Urgency, WorkspaceConfig

CONFIG = WorkspaceConfig(
    business_profile="Online luggage brand.",
    topics=["Orders and delivery"],
    rules=[Rule(id="r1", name="Gifts", when="It is about gifts", action=RuleAction.ALERT)],
    important_contacts=["bigcorp.example"],
)
NOTES = Notes(topic="Orders and delivery", urgency=Urgency.NORMAL, anger=1, summary="s", sure=True)

HISTORY = History(
    corrections=Corrections(
        items=[
            CorrectionExample(
                id="c1",
                subject="Late bag",
                summary="Asks where the bag is",
                field="urgency",
                from_value="normal",
                to_value="high",
            )
        ]
    )
)


def email(sender: str = "a@customer.in") -> Email:
    return Email(id="e1", workspace_id="w1", sender=sender, subject="Order", body="Where is it?")


def stub_model(parsed) -> tuple[AnthropicModel, list[dict]]:
    calls: list[dict] = []

    async def parse(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=parsed)

    client = SimpleNamespace(messages=SimpleNamespace(parse=parse))
    return AnthropicModel(client=client), calls  # type: ignore[arg-type]


async def test_notes_call_sends_the_cached_brand_prompt():
    model, calls = stub_model(NOTES)
    await model.write_notes(email(), "Tripfold", CONFIG)
    (call,) = calls
    assert call["system"] == [
        {
            "type": "text",
            "text": system_prompt("Tripfold", CONFIG),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    expected = email_block(email(), important=CONFIG.is_important(email().sender))
    assert call["messages"] == [{"role": "user", "content": expected}]


async def test_rules_call_shares_the_notes_system_prompt():
    notes_model, notes_calls = stub_model(NOTES)
    await notes_model.write_notes(email(), "Tripfold", CONFIG)
    rules_model, rules_calls = stub_model(_Verdicts(verdicts=[]))
    await rules_model.judge_rules(email(), "Tripfold", CONFIG)
    assert rules_calls[0]["system"] == notes_calls[0]["system"]
    content = rules_calls[0]["messages"][0]["content"]
    assert content.startswith(email_block(email(), important=False))
    assert content.endswith("\n\nAnswer each rule in the <business> block.")


async def test_no_rules_means_no_call():
    model, calls = stub_model(_Verdicts(verdicts=[]))
    config = CONFIG.model_copy(update={"rules": []})
    assert await model.judge_rules(email(), "Tripfold", config) == []
    assert calls == []


async def test_important_sender_is_marked():
    model, calls = stub_model(NOTES)
    await model.write_notes(email("corporate-gifts@bigcorp.example"), "Tripfold", CONFIG)
    assert "(important contact)" in calls[0]["messages"][0]["content"]


async def test_no_history_sends_exactly_the_email_block():
    model, calls = stub_model(NOTES)
    await model.write_notes(email(), "Tripfold", CONFIG, History())
    assert calls[0]["messages"][0]["content"] == email_block(email(), important=False)


async def test_notes_call_sends_history_before_the_email():
    model, calls = stub_model(NOTES)
    await model.write_notes(email(), "Tripfold", CONFIG, HISTORY)
    assert calls[0]["messages"][0]["content"].startswith(history_block(HISTORY) + "\n\n<email>")
    assert calls[0]["system"][0]["text"] == system_prompt("Tripfold", CONFIG)


async def test_rules_call_sends_history_before_the_email():
    model, calls = stub_model(_Verdicts(verdicts=[]))
    await model.judge_rules(email(), "Tripfold", CONFIG, HISTORY)
    content = calls[0]["messages"][0]["content"]
    assert content.startswith(history_block(HISTORY) + "\n\n<email>")
    assert content.endswith("Answer each rule in the <business> block.")
