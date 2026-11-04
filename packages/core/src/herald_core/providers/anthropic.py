"""The Anthropic provider: Claude with structured outputs, called directly."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from anthropic import APIError, AsyncAnthropic
from anthropic.types import ToolResultBlockParam, ToolUseBlock
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

DEFAULT_MODEL = "claude-haiku-5-5"


async def _run(by_name: dict[str, ModelTool], call: ToolUseBlock) -> ToolResultBlockParam:
    """One tool call's result. A failure goes back as an error result, so the model answers
    without that context instead of the email losing its notes."""
    tool = by_name.get(call.name)
    if tool is None:
        return _result(call, f"No tool named {call.name}.", error=True)
    try:
        return _result(call, await tool.run(call.input))
    except ToolError as exc:
        return _result(call, str(exc), error=True)


def _result(call: ToolUseBlock, text: str, *, error: bool = False) -> ToolResultBlockParam:
    return {"type": "tool_result", "tool_use_id": call.id, "content": text, "is_error": error}


class AnthropicModel:
    def __init__(
        self,
        client: AsyncAnthropic | None = None,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
    ) -> None:
        self._client = client or AsyncAnthropic(api_key=api_key)
        self._model = model

    async def _parse[T: BaseModel](
        self, system: str, content: str, output: type[T], tools: Sequence[ModelTool] = ()
    ) -> T:
        by_name = {tool.name: tool for tool in tools}
        # The same tool list for the notes and rules calls, so tools never change a workspace's
        # prompt prefix. Each call's output schema is part of the prefix, so each has its own
        # cache entry.
        offered: dict[str, Any] = {"tools": [tool.definition for tool in tools]} if tools else {}
        messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
        for round_ in range(MAX_TOOL_ROUNDS + 1):
            # The last round takes the tools away, so the model has to answer with the schema.
            last = bool(tools) and round_ == MAX_TOOL_ROUNDS
            choice = {"tool_choice": {"type": "none"}} if last else {}
            try:
                # Marked cacheable: the same brand prompt is sent for every email of a workspace.
                response = await self._client.messages.parse(
                    model=self._model,
                    max_tokens=4096,
                    system=[
                        {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                    ],
                    # A copy: the list grows after the call, and a test client keeps the kwargs.
                    messages=list(messages),
                    output_format=output,
                    **offered,
                    **choice,
                )
            except (APIError, ValidationError) as exc:
                raise ModelError(str(exc)) from exc
            if response.stop_reason != "tool_use":
                break
            # The content goes back as it came: thinking blocks must be returned unchanged.
            messages.append({"role": "assistant", "content": response.content})
            calls = [block for block in response.content if block.type == "tool_use"]
            # Every call gets its result, in one user message, or the API rejects the next turn.
            messages.append({"role": "user", "content": [await _run(by_name, c) for c in calls]})
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise ModelError(f"No structured output (stop_reason={response.stop_reason})")
        return response.parsed_output

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
class AnthropicProvider:
    name: str = "anthropic"
    default_model: str = DEFAULT_MODEL
    api_key_env: str = "ANTHROPIC_API_KEY"

    def build(self, model: str, api_key: str, max_retries: int = 2) -> TriageModel:
        client = AsyncAnthropic(api_key=api_key, max_retries=max_retries)
        return AnthropicModel(client, model=model)


provider = AnthropicProvider()
