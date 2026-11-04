import json
from datetime import datetime

import httpx2
import pytest
from openai import AsyncOpenAI
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel

from herald_core.history import SENDER_HISTORY, SenderHistory
from herald_core.model import ModelError, Verdicts
from herald_core.prompt import RULES_ASK, system_prompt
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
from herald_core.tools import SenderLookup

CONFIG = WorkspaceConfig(
    business_profile="Online luggage brand.",
    topics=["Orders and delivery"],
    rules=[Rule(id="r1", name="Gifts", when="It is about gifts", action=RuleAction.ALERT)],
)
NOTES = Notes(topic="Orders and delivery", urgency=Urgency.NORMAL, anger=1, summary="s", sure=True)
EMAIL = Email(id="e1", workspace_id="w1", sender="a@customer.in", subject="Order", body="Where?")


def completion(
    content=None, *, finish="stop", tool_calls=None, refusal=None, message_extra=None, **top
) -> dict:
    """A chat.completion body in the shape OpenRouter returns."""
    message = {"role": "assistant", "content": content, "refusal": refusal}
    if tool_calls:
        message["tool_calls"] = tool_calls
    message.update(message_extra or {})
    body = {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 1,
        "model": "openai/gpt-oss-20b",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
    }
    return body | top


def answer(model: BaseModel) -> dict:
    return completion(model.model_dump_json())


def tool_call(arguments: str = "{}", name: str = SENDER_HISTORY, id: str = "tc1") -> dict:
    return {"id": id, "type": "function", "function": {"name": name, "arguments": arguments}}


def asking(*calls: dict, **extra) -> dict:
    return completion(finish="tool_calls", tool_calls=list(calls), message_extra=extra)


def stub_model(*bodies, status: int = 200) -> tuple[OpenRouterModel, list[dict]]:
    """A model on the real SDK. The transport answers with `bodies` in order and records the
    JSON of each request it sees."""
    requests: list[dict] = []
    queue = list(bodies)

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(json.loads(request.content))
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return httpx2.Response(status, json=item)

    client = AsyncOpenAI(
        base_url=BASE_URL,
        api_key="sk-test",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    return OpenRouterModel(client=client), requests


async def test_notes_call_sends_schema_and_routing():
    model, calls = stub_model(answer(NOTES))
    assert await model.write_notes(EMAIL, "Tripfold", CONFIG) == NOTES
    (call,) = calls
    assert call["response_format"]["type"] == "json_schema"
    schema = call["response_format"]["json_schema"]
    assert schema["name"] == "Notes"
    assert schema["strict"] is True
    assert schema["schema"] == to_strict_json_schema(Notes)
    assert call["model"] == "openai/gpt-oss-20b"
    assert call["provider"] == {"require_parameters": True}
    assert call["reasoning"] == {"effort": "low"}
    assert call["messages"][0] == {"role": "system", "content": system_prompt("Tripfold", CONFIG)}
    assert call["messages"][1]["role"] == "user"
    assert "tools" not in call


async def test_rules_call_ends_with_rules_ask():
    verdict = RuleVerdict(rule_id="r1", matched=True, quote="a gift")
    model, calls = stub_model(answer(Verdicts(verdicts=[verdict])))
    assert await model.judge_rules(EMAIL, "Tripfold", CONFIG) == [verdict]
    assert calls[0]["messages"][1]["content"].endswith(f"\n\n{RULES_ASK}")
    assert calls[0]["response_format"]["json_schema"]["name"] == "Verdicts"


async def test_no_rules_means_no_call():
    model, calls = stub_model()
    config = CONFIG.model_copy(update={"rules": []})
    assert await model.judge_rules(EMAIL, "Tripfold", config) == []
    assert calls == []


async def test_setup_draft_uses_the_setup_instructions():
    draft = SetupDraft(topics=[TopicDraft(name="Q", meaning="m")], facts=[], guidance=[], rules=[])
    model, calls = stub_model(answer(draft))
    assert await model.suggest_setup("Tripfold", "Luggage") == draft
    assert calls[0]["response_format"]["json_schema"]["name"] == "SetupDraft"
    assert "Name: Tripfold" in calls[0]["messages"][1]["content"]


def sender_lookup() -> SenderLookup:
    history = SenderHistory(
        first_seen=datetime(2026, 9, 12), count_7d=2, count_30d=4, top_topics=[], recent=[]
    )
    return SenderLookup(history)


async def test_tool_round_then_answer():
    lookup = sender_lookup()
    model, calls = stub_model(asking(tool_call()), answer(NOTES))
    await model.write_notes(EMAIL, "Tripfold", CONFIG, tools=[lookup])
    first, second = calls
    assert "tool_choice" not in first
    (tool,) = first["tools"]
    assert tool["type"] == "function"
    assert tool["function"]["strict"] is True
    assert tool["function"]["name"] == SENDER_HISTORY
    assert second["tool_choice"] == "none"
    assert len(second["tools"]) == 1
    assistant, result = second["messages"][2:]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["id"] == "tc1"
    assert result["role"] == "tool"
    assert result["tool_call_id"] == "tc1"
    assert "Error" not in result["content"]
    assert lookup.calls == 1


async def test_reasoning_goes_back_with_the_tool_turn():
    details = [{"type": "reasoning.text", "text": "check the sender", "index": 0}]
    model, calls = stub_model(
        asking(tool_call(), reasoning="check the sender", reasoning_details=details),
        answer(NOTES),
    )
    await model.write_notes(EMAIL, "Tripfold", CONFIG, tools=[sender_lookup()])
    assistant = calls[1]["messages"][2]
    assert assistant["reasoning_details"] == details
    assert assistant["reasoning"] == "check the sender"


async def test_bad_tool_arguments_go_back_as_an_error():
    lookup = SenderLookup(None)
    model, calls = stub_model(asking(tool_call("{not json")), answer(NOTES))
    assert await model.write_notes(EMAIL, "Tripfold", CONFIG, tools=[lookup]) == NOTES
    assert calls[1]["messages"][-1]["content"].startswith("Error: ")
    assert lookup.calls == 0


async def test_tool_failure_and_unknown_tool_go_back_as_errors():
    lookup = SenderLookup(None)  # no history: the tool raises ToolError
    first = asking(tool_call(id="a"), tool_call(name="nope", id="b"))
    model, calls = stub_model(first, answer(NOTES))
    await model.write_notes(EMAIL, "Tripfold", CONFIG, tools=[lookup])
    results = calls[1]["messages"][-2:]
    assert [r["tool_call_id"] for r in results] == ["a", "b"]
    assert all(r["content"].startswith("Error: ") for r in results)


async def test_a_tool_request_on_the_last_round_raises():
    again = asking(tool_call())
    model, _ = stub_model(again, again)
    with pytest.raises(ModelError):
        await model.write_notes(EMAIL, "Tripfold", CONFIG, tools=[SenderLookup(None)])


@pytest.mark.parametrize(
    "body",
    [
        completion(None, refusal="No."),
        completion(None),
        completion("", finish="stop"),
        completion("not json"),
        completion('{"topic": "Orders and delivery"}'),
        completion(NOTES.model_dump_json(), finish="length"),
        completion(None, finish="content_filter"),
        completion(choices=[]),
        completion(choices=None),
        {"error": {"code": 502, "message": "Upstream failed"}},
    ],
    ids=[
        "refusal",
        "null content",
        "empty content",
        "not json",
        "fails validation",
        "length",
        "content filter",
        "empty choices",
        "null choices",
        "error in a 200",
    ],
)
async def test_bad_replies_raise_model_error(body):
    model, _ = stub_model(body)
    with pytest.raises(ModelError):
        await model.write_notes(EMAIL, "Tripfold", CONFIG)


async def test_http_error_raises_model_error():
    model, _ = stub_model({"error": {"message": "Bad key"}}, status=401)
    with pytest.raises(ModelError):
        await model.write_notes(EMAIL, "Tripfold", CONFIG)


async def test_connection_error_raises_model_error():
    model, _ = stub_model(httpx2.ConnectError("down"))
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
