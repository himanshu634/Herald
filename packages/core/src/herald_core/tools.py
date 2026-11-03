"""Tools the triage agent can call for extra context.

A tool is a small async function with typed input and output. `Toolbox` runs them with a time
limit and never lets one fail the email: a bad call gives `None` and the tool's name goes in
`failed`.
"""

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import Protocol

from pydantic import BaseModel

log = logging.getLogger(__name__)


class ToolError(Exception):
    """A tool could not do its job (bad lookup, missing data)."""


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
