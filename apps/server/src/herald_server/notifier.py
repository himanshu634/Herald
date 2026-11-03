"""Notifier implementations. SSE only reaches an open tab; these reach the owner's phone."""

import logging

import httpx

from herald_core.adapters import Alert

log = logging.getLogger(__name__)


class LogNotifier:
    async def send(self, alert: Alert) -> None:
        log.warning("ALERT %s: %s (%s)", alert.title, alert.summary, alert.reason)


class NtfyNotifier:
    def __init__(self, base_url: str, topic: str) -> None:
        self._url = f"{base_url.rstrip('/')}/{topic}"

    async def send(self, alert: Alert) -> None:
        lines = [alert.summary, f"Why: {alert.reason}"]
        if alert.quote:
            lines.append(f'"{alert.quote}"')
        headers = {"Title": alert.title, "Priority": "high", "Tags": "rotating_light"}
        if alert.link:
            headers["Click"] = alert.link
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self._url, content="\n".join(lines), headers=headers)
            response.raise_for_status()
