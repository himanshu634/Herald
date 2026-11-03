"""The agent's tools, bound to one workspace and one email when the toolbox is built."""

from datetime import datetime

from sqlalchemy import Engine

from herald_core.tools import Toolbox
from herald_server.tools.history import CorrectionsTool, SenderHistoryTool, ThreadTool


def build_toolbox(engine: Engine, workspace_id: str, email_id: str, before: datetime) -> Toolbox:
    # The workspace, the email and the cut-off time are fixed here. No tool input can change
    # them, so the model cannot read another tenant's mail or the email it is judging.
    return Toolbox(
        [
            SenderHistoryTool(engine, workspace_id, email_id, before),
            ThreadTool(engine, workspace_id, email_id, before),
            CorrectionsTool(engine, workspace_id, email_id, before),
        ]
    )


__all__ = ["build_toolbox"]
