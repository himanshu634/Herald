"""The OpenRouter provider: any model OpenRouter serves, through the OpenAI-compatible API."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APIError, APIStatusError, AsyncOpenAI, Timeout
from openai.lib._pydantic import to_strict_json_schema
from openai.types.chat.chat_completion import Choice
from pydantic import BaseModel, ValidationError

from herald_core.history import History
from herald_core.model import (
    _SETUP_INSTRUCTIONS,
    MAX_TOOL_ROUNDS,
    REQUEST_RETRIES,
    REQUEST_TIMEOUT,
    RULES_ASK,
    SETUP_TIMEOUT,
    ModelError,
    TriageModel,
    _Verdicts,
    status_kind,
)
from herald_core.model_tools import ModelTool
from herald_core.prompt import system_prompt, user_message
from herald_core.schema import Email, FailureKind, Notes, RuleVerdict, SetupDraft, WorkspaceConfig
from herald_core.tools import ToolError

DEFAULT_MODEL = "openai/gpt-oss-20b"
BASE_URL = "https://openrouter.ai/api/v1"

# require_parameters: route only to endpoints that support the schema and the tools. Without
# it a request can land on an endpoint that ignores the schema. Models that do not reason
# ignore the effort setting.
EXTRA_BODY: dict[str, Any] = {
    "provider": {"require_parameters": True},
    "reasoning": {"effort": "low"},
}


def error_kind(exc: APIError) -> FailureKind:
    """Sorts an OpenAI SDK error from OpenRouter by what trying again can fix."""
    # Timeouts are connection errors in the SDK.
    if isinstance(exc, APIConnectionError):
        return FailureKind.UNAVAILABLE
    if isinstance(exc, APIStatusError):
        return status_kind(exc.status_code)
    return FailureKind.UNREADABLE


def _function_tool(tool: ModelTool) -> dict[str, Any]:
    """The tool in the OpenAI shape, strict so the model keeps to the input schema."""
    definition = tool.definition
    return {
        "type": "function",
        "function": {
            "name": definition["name"],
            "description": definition.get("description", ""),
            "parameters": definition["input_schema"],
            "strict": True,
        },
    }


async def _run(by_name: dict[str, ModelTool], name: str, arguments: str) -> str:
    """One tool call's result text. A failure goes back as error text, so the model answers
    without that context instead of the email losing its notes."""
    tool = by_name.get(name)
    if tool is None:
        return f"Error: No tool named {name}."
    try:
        args = json.loads(arguments or "{}")
        if not isinstance(args, dict):
            raise ValueError("not an object")
    except ValueError:
        # Models sometimes send broken JSON; they can retry or answer without the tool.
        return "Error: The tool arguments were not a valid JSON object."
    try:
        return await tool.run(args)
    except ToolError as exc:
        return f"Error: {exc}"


class OpenRouterModel:
    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        max_retries: int = REQUEST_RETRIES,
    ) -> None:
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=BASE_URL,
            timeout=Timeout(REQUEST_TIMEOUT, connect=5.0),
            max_retries=max_retries,
            default_headers={"X-Title": "Herald"},
        )
        self._model = model

    async def _parse[T: BaseModel](
        self,
        system: str,
        content: str,
        output: type[T],
        tools: Sequence[ModelTool] = (),
        request_timeout: float | None = None,
    ) -> T:
        by_name = {tool.name: tool for tool in tools}
        offered: dict[str, Any] = {"tools": [_function_tool(t) for t in tools]} if tools else {}
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]
        for round_ in range(MAX_TOOL_ROUNDS + 1):
            # The last round takes the tools away, so the model has to answer with the schema.
            last = bool(tools) and round_ == MAX_TOOL_ROUNDS
            choice = {"tool_choice": "none"} if last else {}
            # Some hosts behind OpenRouter return only the model's reasoning, with no answer and
            # no tool call. One empty reply gets one more try with that host left out; OpenRouter
            # tends to send a retry back to the same host otherwise. A second empty reply is
            # reported as unavailable, so the worker retries the email later.
            ignore: list[str] = []
            for _ in range(2):
                picked, host = await self._complete(
                    messages, output, request_timeout, offered, choice, ignore
                )
                message = picked.message
                if message.content or message.tool_calls or message.refusal:
                    break
                if host:
                    ignore.append(host)
            else:
                raise ModelError(
                    f"Empty reply twice (finish_reason={picked.finish_reason})",
                    FailureKind.UNAVAILABLE,
                )
            if not message.tool_calls:
                break
            if last:
                raise ModelError("The model asked for a tool on the last round")
            assistant: dict[str, Any] = {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in message.tool_calls
                ],
            }
            # Reasoning models keep their chain across the tool round only if the reasoning
            # they returned goes back with the assistant turn.
            extra = message.model_extra or {}
            for key in ("reasoning", "reasoning_details"):
                if extra.get(key) is not None:
                    assistant[key] = extra[key]
            messages.append(assistant)
            # Every call gets its result, or the API rejects the next turn.
            for call in message.tool_calls:
                result = await _run(by_name, call.function.name, call.function.arguments)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        if message.refusal or not message.content:
            raise ModelError(f"No structured output (finish_reason={picked.finish_reason})")
        try:
            return output.model_validate_json(message.content)
        except ValidationError as exc:
            raise ModelError(str(exc)) from exc

    async def _complete(
        self,
        messages: list[dict[str, Any]],
        output: type[BaseModel],
        request_timeout: float | None,
        offered: dict[str, Any],
        choice: dict[str, Any],
        ignore: list[str],
    ) -> tuple[Choice, str | None]:
        """One request: the first choice and the host that served it. Every failure, and a
        reply that stopped early, raises ModelError."""
        extra_body = EXTRA_BODY
        if ignore:
            extra_body = {**EXTRA_BODY, "provider": {**EXTRA_BODY["provider"], "ignore": ignore}}
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                # A copy: the list grows after the call.
                messages=list(messages),
                # `create`, not `parse`: `parse` runs json.loads on tool arguments inside the
                # SDK, so broken arguments would fail the call instead of reaching `_run`.
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": output.__name__,
                        "schema": to_strict_json_schema(output),
                        "strict": True,
                    },
                },
                extra_body=extra_body,
                **({"timeout": request_timeout} if request_timeout else {}),
                **offered,
                **choice,
            )
        except APIError as exc:
            raise ModelError(str(exc), error_kind(exc)) from exc
        except Exception as exc:
            # An error body inside a 200, or a null `choices`, fails in the SDK's parsing.
            raise ModelError(f"Bad response: {exc}") from exc
        if not response.choices:
            raise ModelError("No choices in the response")
        picked = response.choices[0]
        if picked.finish_reason in ("length", "content_filter"):
            raise ModelError(f"The model stopped early (finish_reason={picked.finish_reason})")
        # OpenRouter names the host in a top-level `provider` field the SDK does not model.
        return picked, (response.model_extra or {}).get("provider")

    async def write_notes(
        self,
        email: Email,
        business_name: str,
        config: WorkspaceConfig,
        history: History | None = None,
        tools: Sequence[ModelTool] = (),
    ) -> Notes:
        content = user_message(email, config.is_important(email.sender), history or History())
        return await self._parse(system_prompt(business_name, config), content, Notes, tools)

    async def judge_rules(
        self,
        email: Email,
        business_name: str,
        config: WorkspaceConfig,
        history: History | None = None,
        tools: Sequence[ModelTool] = (),
    ) -> list[RuleVerdict]:
        if not config.rules:
            return []
        block = user_message(email, config.is_important(email.sender), history or History())
        content = f"{block}\n\n{RULES_ASK}"
        system = system_prompt(business_name, config)
        return (await self._parse(system, content, _Verdicts, tools)).verdicts

    async def suggest_setup(self, name: str, description: str) -> SetupDraft:
        content = f"<business>\nName: {name}\n\n{description}\n</business>"
        return await self._parse(
            _SETUP_INSTRUCTIONS, content, SetupDraft, request_timeout=SETUP_TIMEOUT
        )


@dataclass(frozen=True)
class OpenRouterProvider:
    name: str = "openrouter"
    default_model: str = DEFAULT_MODEL
    api_key_env: str = "OPENROUTER_API_KEY"

    def build(self, model: str, api_key: str, max_retries: int = REQUEST_RETRIES) -> TriageModel:
        return OpenRouterModel(model=model, api_key=api_key, max_retries=max_retries)


provider = OpenRouterProvider()
