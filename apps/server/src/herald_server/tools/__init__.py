"""The agent's tools, bound to one email when the toolbox is built. Each calls the API."""

from herald_core.tools import Toolbox
from herald_server.internal.client import AgentApi
from herald_server.tools.corrections import CorrectionsTool
from herald_server.tools.sender_history import SenderHistoryTool
from herald_server.tools.thread import ThreadTool


def build_toolbox(api: AgentApi, email_id: str) -> Toolbox:
    # The email is fixed here and no tool input can change it. The API derives the workspace
    # and the cut-off time from it, so the model cannot read another tenant's mail.
    return Toolbox(
        [
            SenderHistoryTool(api, email_id),
            ThreadTool(api, email_id),
            CorrectionsTool(api, email_id),
        ]
    )


__all__ = ["build_toolbox"]
