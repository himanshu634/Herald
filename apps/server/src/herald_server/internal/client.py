"""The worker's client for the internal routes. The pipeline and its tools use only this."""

from typing import Self
from urllib.parse import quote

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from herald_core.history import (
    Corrections,
    CorrectionsIn,
    SenderHistory,
    SenderHistoryIn,
    Thread,
    ThreadIn,
)
from herald_server.internal.schemas import TriageInput, TriageResult
from herald_server.internal.token import TOKEN_HEADER

PREFIX = "/internal/v1"
TIMEOUT = 10.0


class ApiUnavailable(Exception):
    """The API could not take the call, and trying it again later is safe."""


class AgentApi:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    @classmethod
    def connect(cls, base_url: str, token: str) -> Self:
        return cls(
            httpx.AsyncClient(base_url=base_url, headers={TOKEN_HEADER: token}, timeout=TIMEOUT)
        )

    @classmethod
    def in_process(cls, app: FastAPI, token: str) -> Self:
        # Inline queue and tests: the same routes, called in memory with no network.
        transport = httpx.ASGITransport(app=app)
        return cls(
            httpx.AsyncClient(
                transport=transport,
                base_url="http://herald",
                headers={TOKEN_HEADER: token},
                timeout=TIMEOUT,
            )
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def triage_input(self, email_id: str) -> TriageInput:
        return await self._get(email_id, "triage-input", TriageInput)

    async def save_triage_result(self, email_id: str, result: TriageResult) -> None:
        try:
            response = await self._http.post(
                self._path(email_id, "triage-result"),
                content=result.model_dump_json(),
                headers={"content-type": "application/json"},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # The request never reached the API, so nothing was saved and a retry cannot
            # publish the events twice. Any later failure may have committed, so it is raised
            # as it is and not retried.
            raise ApiUnavailable(type(exc).__name__) from exc
        response.raise_for_status()

    async def sender_history(self, email_id: str, args: SenderHistoryIn) -> SenderHistory:
        return await self._get(email_id, "history/sender", SenderHistory, args)

    async def thread(self, email_id: str, args: ThreadIn) -> Thread:
        return await self._get(email_id, "history/thread", Thread, args)

    async def corrections(self, email_id: str, args: CorrectionsIn) -> Corrections:
        return await self._get(email_id, "history/corrections", Corrections, args)

    def _path(self, email_id: str, route: str) -> str:
        return f"{PREFIX}/emails/{quote(email_id, safe='')}/{route}"

    async def _get[Out: BaseModel](
        self, email_id: str, route: str, out: type[Out], args: BaseModel | None = None
    ) -> Out:
        try:
            response = await self._http.get(
                self._path(email_id, route), params=args.model_dump() if args else None
            )
        except httpx.TransportError as exc:
            # Reads change nothing, so any network failure is safe to retry.
            raise ApiUnavailable(type(exc).__name__) from exc
        if response.status_code >= 500:
            raise ApiUnavailable(f"{route} answered {response.status_code}")
        response.raise_for_status()
        return out.model_validate_json(response.content)
