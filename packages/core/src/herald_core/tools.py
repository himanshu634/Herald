"""The two kinds of tool triage uses.

Code tools run before the model reads the email (`gather_context`). Each is a small async
function with typed input and output. `Toolbox` runs them with a time limit and never lets one
fail the email: a bad call gives `None` and the tool's name goes in `failed`.

Model tools are the ones the model may call while it reads an email, when it decides it needs
more context. A model tool answers with text the model reads, and a node builds a fresh one for
each call so it can see whether the model used it.
"""

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import Any, Protocol

from anthropic.types import ToolParam
from pydantic import BaseModel

from herald_core.history import SENDER_HISTORY, SenderHistory
from herald_core.prompt import sender_history_text

log = logging.getLogger(__name__)


class ToolError(Exception):
    """A tool could not do its job (bad lookup, missing data)."""


# Code tools


class Tool[In: BaseModel, Out: BaseModel](Protocol):
    name: str
    description: str
    input_model: type[In]
    output_model: type[Out]

    async def run(self, args: In) -> Out: ...


class Toolbox:
    def __init__(self, tools: Iterable[Tool], timeout: float = 2.0) -> None:
        self._tools = {tool.name: tool for tool in tools}
        self.timeout = timeout
        self.failed: list[str] = []
        self.ms: dict[str, int] = {}

    async def call(self, name: str, args: BaseModel) -> BaseModel | None:
        tool = self._tools.get(name)
        if tool is None:
            # An empty toolbox is normal (tests, fake setup), so this is not a failure.
            return None
        start = time.monotonic()
        try:
            if not isinstance(args, tool.input_model):
                raise ToolError(
                    f"{name} got {type(args).__name__}, not {tool.input_model.__name__}"
                )
            async with asyncio.timeout(self.timeout):
                result = await tool.run(args)
            if not isinstance(result, tool.output_model):
                raise ToolError(f"{name} returned {type(result).__name__}")
            return result
        except Exception:
            # Broad on purpose: history only adds context, and must never cost an email its
            # triage. Whatever goes wrong, the caller carries on without this tool's output.
            log.exception("tool %s failed", name)
            self.failed.append(name)
            return None
        finally:
            self.ms[name] = round((time.monotonic() - start) * 1000)


# Model tools


class ModelTool(Protocol):
    name: str
    definition: ToolParam
    calls: int

    async def run(self, args: dict[str, Any]) -> str:
        """The text the model reads. Raises ToolError when there is nothing to give."""
        ...


# Fixed text with nothing from the email or the business in it: tools come before the system
# prompt in the cache key, so a byte that changes per email would end the shared cache entry.
SENDER_HISTORY_TOOL: ToolParam = {
    "name": SENDER_HISTORY,
    "description": (
        "Earlier emails from this email's sender to this business: how many in the last 7 and "
        "30 days, when they first wrote, their usual topics and their latest few emails. Call "
        "it when knowing whether this is a repeat or first-time sender would change your notes "
        "or a rule answer: a follow-up or a chase, a customer who says it is not the first "
        "time, or a rule about repeat contact. Do not call it for an email you can judge on "
        "its own."
    ),
    # No inputs on purpose. The sender is always this email's own, so text in the email cannot
    # steer the model into reading another customer's mail.
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    "strict": True,
}


class SenderLookup:
    """Answers sender_history from what `gather_context` already fetched.

    `decide` needs the sender history for its repeat count whatever the model does, so it is
    fetched in code anyway. Serving the model from that copy saves a second request and keeps
    the model's view and decide's count the same.
    """

    name = SENDER_HISTORY
    definition = SENDER_HISTORY_TOOL

    def __init__(self, sender: SenderHistory | None) -> None:
        self._sender = sender
        self.calls = 0

    async def run(self, args: dict[str, Any]) -> str:
        self.calls += 1
        if self._sender is None:
            # The fetch failed or timed out. Say so, rather than "no earlier emails", which
            # would tell the model a regular customer is new.
            raise ToolError("Sender history is not available right now.")
        return sender_history_text(self._sender)


def asked(node: str, *tools: ModelTool) -> list[str]:
    """One "node:tool" entry for each call the model made, for `email.context.asked`."""
    return [f"{node}:{tool.name}" for tool in tools for _ in range(tool.calls)]
