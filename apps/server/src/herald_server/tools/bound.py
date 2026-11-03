"""The scope every history tool shares: the email being judged, fixed when the toolbox is built."""

from herald_server.internal.client import AgentApi


class Bound:
    """The API looks this email up and keeps each query to its workspace and to mail received
    before it, so no tool input can reach another tenant or the email being judged."""

    def __init__(self, api: AgentApi, email_id: str) -> None:
        self.api = api
        self.email_id = email_id
