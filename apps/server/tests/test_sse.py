"""SSE over a real socket: ASGITransport buffers whole responses, so it cannot read a stream."""

import asyncio
import json
import socket

import httpx
import uvicorn

from herald_server.api.main import create_app


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def read_events(response: httpx.Response, count: int) -> list[dict]:
    events, current = [], {}
    async for line in response.aiter_lines():
        if not line:
            if "event" in current:
                events.append(current)
                if len(events) == count:
                    return events
            current = {}
        elif not line.startswith(":"):
            key, _, value = line.partition(": ")
            current[key] = value
    return events


async def test_events_stream_and_replay(settings):
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), port=port, log_level="warning", lifespan="on")
    )
    serving = asyncio.create_task(server.serve())
    base = f"http://127.0.0.1:{port}/api"
    try:
        async with httpx.AsyncClient(base_url=base, timeout=10) as client:
            while not server.started:  # noqa: ASYNC110 - uvicorn exposes no startup event
                await asyncio.sleep(0.05)
            ws = (await client.post("/workspaces/demo")).json()["id"]

            async with client.stream("GET", f"/workspaces/{ws}/events") as stream:
                await asyncio.sleep(0.2)  # let the subscription register
                await client.post(
                    f"/workspaces/{ws}/emails",
                    json={"sender": "a@b.in", "subject": "Order", "body": "Where is it?"},
                )
                events = await asyncio.wait_for(read_events(stream, 2), timeout=5)
            assert [e["event"] for e in events] == ["email.received", "email.noted"]
            assert json.loads(events[1]["data"])["status"] == "inbox"

            # Reconnect with Last-Event-ID 0: both events are replayed from the database.
            headers = {"Last-Event-ID": "0"}
            async with client.stream("GET", f"/workspaces/{ws}/events", headers=headers) as again:
                replayed = await asyncio.wait_for(read_events(again, 2), timeout=5)
            assert [e["id"] for e in replayed] == [events[0]["id"], events[1]["id"]]
    finally:
        server.should_exit = True
        await serving
