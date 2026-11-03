import asyncio

from pydantic import BaseModel

from herald_core.tools import Toolbox, ToolError


class EchoIn(BaseModel):
    text: str


class EchoOut(BaseModel):
    text: str


class OtherIn(BaseModel):
    pass


class EchoTool:
    name = "echo"
    description = "Echo the text back."
    input_model = EchoIn
    output_model = EchoOut

    async def run(self, args: EchoIn) -> EchoOut:
        return EchoOut(text=args.text)


class BoomTool(EchoTool):
    name = "boom"

    async def run(self, args: EchoIn) -> EchoOut:
        raise ToolError("nope")


class SlowTool(EchoTool):
    name = "slow"

    async def run(self, args: EchoIn) -> EchoOut:
        await asyncio.sleep(1)
        return EchoOut(text=args.text)


class WrongOutTool(EchoTool):
    name = "wrong_out"

    async def run(self, args: EchoIn) -> EchoOut:
        return EchoIn(text=args.text)  # type: ignore[return-value]


async def test_call_returns_the_tool_output():
    box = Toolbox([EchoTool()])
    assert await box.call("echo", EchoIn(text="hi")) == EchoOut(text="hi")
    assert "echo" in box.ms and box.failed == []


async def test_unknown_tool_is_none_and_not_failed():
    box = Toolbox([])
    assert await box.call("nope", EchoIn(text="x")) is None
    assert box.failed == [] and box.ms == {}


async def test_tool_error_is_none_and_failed():
    box = Toolbox([BoomTool()])
    assert await box.call("boom", EchoIn(text="x")) is None
    assert box.failed == ["boom"] and "boom" in box.ms


async def test_timeout_is_none_and_failed():
    box = Toolbox([SlowTool()], timeout=0.01)
    assert await box.call("slow", EchoIn(text="x")) is None
    assert box.failed == ["slow"] and "slow" in box.ms


async def test_wrong_input_type_is_failed():
    box = Toolbox([EchoTool()])
    assert await box.call("echo", OtherIn()) is None
    assert box.failed == ["echo"]


async def test_wrong_output_type_is_failed():
    box = Toolbox([WrongOutTool()])
    assert await box.call("wrong_out", EchoIn(text="x")) is None
    assert box.failed == ["wrong_out"]
