"""The OpenRouter provider: any model OpenRouter serves, through the OpenAI-compatible API."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from openai import APIError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from herald_core.history import History
from herald_core.model import (
    _SETUP_INSTRUCTIONS,
    MAX_TOOL_ROUNDS,
    RULES_ASK,
    ModelError,
    TriageModel,
    _Verdicts,
)
from herald_core.model_tools import ModelTool
from herald_core.prompt import system_prompt, user_message
from herald_core.schema import Email, Notes, RuleVerdict, SetupDraft, WorkspaceConfig
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


def _function_tool(tool: ModelTool) -> dict[str, Any]:
    """The tool in the OpenAI shape. `parse()` rejects function tools that are not strict."""
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
    def __init__(self, client: AsyncOpenAI | None = None, model: str = DEFAULT_MODEL) -> None:
        self._client = client or AsyncOpenAI(base_url=BASE_URL)
        self._model = model

    async def _parse[T: BaseModel](
        self, system: str, content: str, output: type[T], tools: Sequence[ModelTool] = ()
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
            try:
                response = await self._client.chat.completions.parse(
                    model=self._model,
                    # A copy: the list grows after the call, and a test client keeps the kwargs.
                    messages=list(messages),
                    response_format=output,
                    extra_body=EXTRA_BODY,
                    **offered,
                    **choice,
                )
            except (APIError, ValidationError) as exc:
                raise ModelError(str(exc)) from exc
            if not response.choices:
                raise ModelError("No choices in the response")
            picked = response.choices[0]
            message = picked.message
            if picked.finish_reason != "tool_calls" or not message.tool_calls:
                break
            if last:
                raise ModelError("The model asked for a tool on the last round")
            # Every call gets its result, or the API rejects the next turn.
            messages.append(
                {
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
            )
            for call in message.tool_calls:
                result = await _run(by_name, call.function.name, call.function.arguments)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        if message.refusal or message.parsed is None:
            raise ModelError(f"No structured output (finish_reason={picked.finish_reason})")
        return message.parsed

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
        return await self._parse(_SETUP_INSTRUCTIONS, content, SetupDraft)


@dataclass(frozen=True)
class OpenRouterProvider:
    name: str = "openrouter"
    default_model: str = DEFAULT_MODEL
    api_key_env: str = "OPENROUTER_API_KEY"

    def build(self, model: str, api_key: str, max_retries: int = 2) -> TriageModel:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=BASE_URL,
            max_retries=max_retries,
            default_headers={"X-Title": "Herald"},
        )
        return OpenRouterModel(client, model=model)


provider = OpenRouterProvider()
