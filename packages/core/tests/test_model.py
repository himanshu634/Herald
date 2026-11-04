from datetime import datetime
from types import SimpleNamespace

import pytest

from herald_core.history import (
    SENDER_HISTORY,
    CorrectionExample,
    Corrections,
    History,
    SenderHistory,
)
from herald_core.model import ModelError, Verdicts
from herald_core.prompt import email_block, history_block, system_prompt
from herald_core.providers.anthropic import AnthropicModel
from herald_core.schema import Email, Notes, Rule, RuleAction, Urgency, WorkspaceConfig
from herald_core.tools import SENDER_HISTORY_TOOL, SenderLookup, ToolError

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


def stub_model(*replies) -> tuple[AnthropicModel, list[dict]]:
    """A model whose client answers with `replies` in order. A reply is the parsed output, or
    a list of content blocks for a turn that stops to call tools."""
    calls: list[dict] = []
    queue = list(replies)

    async def parse(**kwargs):
        calls.append(kwargs)
        reply = queue.pop(0)
        if isinstance(reply, list):
            return SimpleNamespace(stop_reason="tool_use", parsed_output=None, content=reply)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=reply, content=[])

    client = SimpleNamespace(messages=SimpleNamespace(parse=parse))
    return AnthropicModel(client=client), calls  # type: ignore[arg-type]


def tool_use(name: str = SENDER_HISTORY, id: str = "tu1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id, name=name, input={})


SENDER = SenderHistory(
    first_seen=datetime(2026, 9, 12),
    count_7d=2,
    count_30d=4,
    top_topics=["Orders and delivery"],
    recent=[],
)


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
    rules_model, rules_calls = stub_model(Verdicts(verdicts=[]))
    await rules_model.judge_rules(email(), "Tripfold", CONFIG)
    assert rules_calls[0]["system"] == notes_calls[0]["system"]
    content = rules_calls[0]["messages"][0]["content"]
    assert content.startswith(email_block(email(), important=False))
    assert content.endswith("\n\nAnswer each rule in the <business> block.")


async def test_no_rules_means_no_call():
    model, calls = stub_model(Verdicts(verdicts=[]))
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
    model, calls = stub_model(Verdicts(verdicts=[]))
    await model.judge_rules(email(), "Tripfold", CONFIG, HISTORY)
    content = calls[0]["messages"][0]["content"]
    assert content.startswith(history_block(HISTORY) + "\n\n<email>")
    assert content.endswith("Answer each rule in the <business> block.")


def test_a_sure_note_carries_no_question():
    notes = Notes.model_validate(
        NOTES.model_dump() | {"question": "Why?", "fact_draft": "Because."}
    )
    assert (notes.question, notes.fact_draft) == (None, None)


def test_an_unsure_note_keeps_a_trimmed_question_and_draft():
    notes = Notes.model_validate(
        NOTES.model_dump() | {"sure": False, "question": "  Why?  ", "fact_draft": "x" * 250}
    )
    assert notes.question == "Why?"
    assert notes.fact_draft == "x" * 200


async def test_sender_history_is_not_in_the_prompt():
    model, calls = stub_model(NOTES)
    await model.write_notes(email(), "Tripfold", CONFIG, History(sender=SENDER))
    assert calls[0]["messages"][0]["content"] == email_block(email(), important=False)


async def test_no_tools_sends_no_tool_fields():
    model, calls = stub_model(NOTES)
    await model.write_notes(email(), "Tripfold", CONFIG)
    assert "tools" not in calls[0] and "tool_choice" not in calls[0]


async def test_an_unused_tool_costs_one_call():
    model, calls = stub_model(NOTES)
    lookup = SenderLookup(SENDER)
    assert await model.write_notes(email(), "Tripfold", CONFIG, tools=[lookup]) == NOTES
    (call,) = calls
    assert call["tools"] == [SENDER_HISTORY_TOOL]
    assert "tool_choice" not in call
    assert lookup.calls == 0


async def test_tool_call_result_goes_back_and_the_model_must_answer():
    turn = [SimpleNamespace(type="thinking", thinking=""), tool_use()]
    model, calls = stub_model(turn, NOTES)
    lookup = SenderLookup(SENDER)
    assert await model.write_notes(email(), "Tripfold", CONFIG, tools=[lookup]) == NOTES
    first, second = calls
    assert lookup.calls == 1
    assert len(first["messages"]) == 1  # the copy sent, not the list that grew after
    user, assistant, results = second["messages"]
    assert assistant == {"role": "assistant", "content": turn}  # thinking kept as it came
    (result,) = results["content"]
    assert result["tool_use_id"] == "tu1" and result["is_error"] is False
    assert result["content"].startswith("<history>\nSender: first seen 2026-09-12.")
    # Same tools on both rounds; the last one takes them away so the schema answer comes back.
    assert second["tools"] == first["tools"] == [SENDER_HISTORY_TOOL]
    assert second["tool_choice"] == {"type": "none"}


async def test_every_parallel_call_gets_a_result_in_one_message():
    model, calls = stub_model([tool_use(id="a"), tool_use("nope", id="b")], NOTES)
    await model.write_notes(email(), "Tripfold", CONFIG, tools=[SenderLookup(SENDER)])
    results = calls[1]["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b"]
    assert [r["is_error"] for r in results] == [False, True]


async def test_failed_fetch_goes_back_as_an_error():
    model, calls = stub_model([tool_use()], NOTES)
    assert await model.write_notes(email(), "Tripfold", CONFIG, tools=[SenderLookup(None)]) == NOTES
    (result,) = calls[1]["messages"][2]["content"]
    assert result["is_error"] is True
    assert result["content"] == "Sender history is not available right now."


async def test_no_answer_after_the_last_round_is_a_model_error():
    model, _ = stub_model([tool_use()], [tool_use(id="tu2")])
    with pytest.raises(ModelError):
        await model.write_notes(email(), "Tripfold", CONFIG, tools=[SenderLookup(SENDER)])


async def test_rules_call_offers_the_same_tools():
    notes_model, notes_calls = stub_model(NOTES)
    await notes_model.write_notes(email(), "Tripfold", CONFIG, tools=[SenderLookup(SENDER)])
    rules_model, rules_calls = stub_model(Verdicts(verdicts=[]))
    await rules_model.judge_rules(email(), "Tripfold", CONFIG, tools=[SenderLookup(None)])
    # Byte-identical tools keep the two calls on one cache entry.
    assert rules_calls[0]["tools"] == notes_calls[0]["tools"]


async def test_lookup_for_a_new_sender():
    empty = SenderHistory(first_seen=None, count_7d=0, count_30d=0, top_topics=[], recent=[])
    assert await SenderLookup(empty).run({}) == "No earlier emails from this sender."


async def test_lookup_without_a_fetch_raises():
    with pytest.raises(ToolError):
        await SenderLookup(None).run({})


def test_sender_tool_takes_no_input():
    schema = SENDER_HISTORY_TOOL["input_schema"]
    assert schema["properties"] == {} and schema["additionalProperties"] is False
    assert SENDER_HISTORY_TOOL["strict"] is True
