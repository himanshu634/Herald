from datetime import datetime
from types import SimpleNamespace

import httpx
import openai
import pytest

from herald_core.history import SENDER_HISTORY, SenderHistory
from herald_core.model import RULES_ASK, ModelError, _Verdicts
from herald_core.model_tools import SenderLookup
from herald_core.prompt import system_prompt
from herald_core.providers import load_provider
from herald_core.providers.openrouter import BASE_URL, OpenRouterModel
from herald_core.schema import (
    Email,
    Notes,
    Rule,
    RuleAction,
    RuleVerdict,
    SetupDraft,
    TopicDraft,
    Urgency,
    WorkspaceConfig,
)

CONFIG = WorkspaceConfig(
    business_profile="Online luggage brand.",
    topics=["Orders and delivery"],
    rules=[Rule(id="r1", name="Gifts", when="It is about gifts", action=RuleAction.ALERT)],
)
NOTES = Notes(topic="Orders and delivery", urgency=Urgency.NORMAL, anger=1, summary="s", sure=True)
EMAIL = Email(id="e1", workspace_id="w1", sender="a@customer.in", subject="Order", body="Where?")


def reply(parsed=None, *, finish="stop", tool_calls=None, refusal=None):
    message = SimpleNamespace(
        content=None, parsed=parsed, refusal=refusal, tool_calls=tool_calls or None
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish)])


def tool_call(arguments: str = "{}", name: str = SENDER_HISTORY, id: str = "tc1"):
    return SimpleNamespace(id=id, function=SimpleNamespace(name=name, arguments=arguments))


def stub_model(*replies) -> tuple[OpenRouterModel, list[dict]]:
    """A model whose client answers with `replies` in order; an exception is raised instead."""
    calls: list[dict] = []
    queue = list(replies)

    async def parse(**kwargs):
        calls.append(kwargs)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    return OpenRouterModel(client=client), calls  # type: ignore[arg-type]


async def test_notes_call_sends_schema_and_routing():
    model, calls = stub_model(reply(NOTES))
    assert await model.write_notes(EMAIL, "Tripfold", CONFIG) == NOTES
    (call,) = calls
    assert call["response_format"] is Notes
    assert call["model"] == "openai/gpt-oss-20b"
    assert call["extra_body"] == {
        "provider": {"require_parameters": True},
        "reasoning": {"effort": "low"},
    }
    assert call["messages"][0] == {"role": "system", "content": system_prompt("Tripfold", CONFIG)}
    assert call["messages"][1]["role"] == "user"
    assert "tools" not in call


async def test_rules_call_ends_with_rules_ask():
    verdict = RuleVerdict(rule_id="r1", matched=True, quote="a gift")
    model, calls = stub_model(reply(_Verdicts(verdicts=[verdict])))
    assert await model.judge_rules(EMAIL, "Tripfold", CONFIG) == [verdict]
    assert calls[0]["messages"][1]["content"].endswith(f"\n\n{RULES_ASK}")
    assert calls[0]["response_format"] is _Verdicts


async def test_no_rules_means_no_call():
    model, calls = stub_model()
    config = CONFIG.model_copy(update={"rules": []})
    assert await model.judge_rules(EMAIL, "Tripfold", config) == []
    assert calls == []


async def test_setup_draft_uses_the_setup_instructions():
    draft = SetupDraft(topics=[TopicDraft(name="Q", meaning="m")], facts=[], guidance=[], rules=[])
    model, calls = stub_model(reply(draft))
    assert await model.suggest_setup("Tripfold", "Luggage") == draft
    assert calls[0]["response_format"] is SetupDraft
    assert "Name: Tripfold" in calls[0]["messages"][1]["content"]


async def test_tool_round_then_answer():
    lookup = SenderLookup(
        SenderHistory(
            first_seen=datetime(2026, 9, 12), count_7d=2, count_30d=4, top_topics=[], recent=[]
        )
    )
    model, calls = stub_model(reply(finish="tool_calls", tool_calls=[tool_call()]), reply(NOTES))
    await model.write_notes(EMAIL, "Tripfold", CONFIG, tools=[lookup])
    first, second = calls
    assert "tool_choice" not in first
    (tool,) = first["tools"]
    assert tool["type"] == "function"
    assert tool["function"]["strict"] is True
    assert tool["function"]["name"] == SENDER_HISTORY
    assert second["tool_choice"] == "none"
    assistant, result = second["messages"][2:]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["id"] == "tc1"
    assert result["role"] == "tool"
    assert result["tool_call_id"] == "tc1"
    assert "Error" not in result["content"]
    assert lookup.calls == 1


async def test_bad_tool_arguments_go_back_as_an_error():
    lookup = SenderLookup(None)
    model, calls = stub_model(
        reply(finish="tool_calls", tool_calls=[tool_call("{not json")]), reply(NOTES)
    )
    assert await model.write_notes(EMAIL, "Tripfold", CONFIG, tools=[lookup]) == NOTES
    assert calls[1]["messages"][-1]["content"].startswith("Error: ")
    assert lookup.calls == 0


async def test_tool_failure_and_unknown_tool_go_back_as_errors():
    lookup = SenderLookup(None)  # no history: the tool raises ToolError
    calls_in = [tool_call(id="a"), tool_call(name="nope", id="b")]
    model, calls = stub_model(reply(finish="tool_calls", tool_calls=calls_in), reply(NOTES))
    await model.write_notes(EMAIL, "Tripfold", CONFIG, tools=[lookup])
    results = calls[1]["messages"][-2:]
    assert [r["tool_call_id"] for r in results] == ["a", "b"]
    assert all(r["content"].startswith("Error: ") for r in results)


async def test_a_tool_request_on_the_last_round_raises():
    lookup = SenderLookup(None)
    again = reply(finish="tool_calls", tool_calls=[tool_call()])
    model, _ = stub_model(again, again)
    with pytest.raises(ModelError):
        await model.write_notes(EMAIL, "Tripfold", CONFIG, tools=[lookup])


async def test_refusal_raises_model_error():
    model, _ = stub_model(reply(None, refusal="No."))
    with pytest.raises(ModelError):
        await model.write_notes(EMAIL, "Tripfold", CONFIG)


async def test_empty_parse_raises_model_error():
    model, _ = stub_model(reply(None, finish="length"))
    with pytest.raises(ModelError, match="length"):
        await model.write_notes(EMAIL, "Tripfold", CONFIG)


async def test_api_error_raises_model_error():
    error = openai.APIConnectionError(request=httpx.Request("POST", BASE_URL))
    model, _ = stub_model(error)
    with pytest.raises(ModelError):
        await model.write_notes(EMAIL, "Tripfold", CONFIG)


def test_openrouter_provider():
    provider = load_provider("openrouter")
    assert provider.name == "openrouter"
    assert provider.default_model == "openai/gpt-oss-20b"
    assert provider.api_key_env == "OPENROUTER_API_KEY"
    assert isinstance(provider.build("openai/gpt-oss-20b", "sk-or-test"), OpenRouterModel)


def test_provider_client_points_at_openrouter():
    model = load_provider("openrouter").build("m", "sk-or-test", max_retries=6)
    client = model._client  # type: ignore[attr-defined]
    assert str(client.base_url).startswith(BASE_URL)
    assert client.max_retries == 6
    assert client.default_headers["X-Title"] == "Herald"
