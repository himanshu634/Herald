"""The owner's replies to one email: send one, list them."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from herald_server.api.deps import ServicesDep, WorkspaceDep
from herald_server.api.schemas import ReplyIn, ReplyOut
from herald_server.models import Reply, ReplyStatus
from herald_server.replies import (
    EmailNotFound,
    ReplyBlocked,
    is_stale,
    list_replies,
    send_reply,
)

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/emails/{email_id}/replies", tags=["replies"]
)

EmailId = Annotated[str, Path()]


def _out(reply: Reply) -> ReplyOut:
    out = ReplyOut.model_validate(reply, from_attributes=True)
    # Every reply the API returns passes here. A stale SENDING row's process died, so it is
    # reported as unknown, or the panel would say "Sending…" forever. Nothing is written: the
    # next POST for this email makes it durable and stages its reply.status event.
    if is_stale(reply):
        out = out.model_copy(update={"status": ReplyStatus.UNKNOWN, "error": "unknown"})
    return out


@router.post("")
async def post_reply(
    data: ReplyIn, workspace: WorkspaceDep, services: ServicesDep, email_id: EmailId
) -> ReplyOut:
    """Send the owner's reply. The outcome is the reply's `status`, so a failed send is a 200."""
    try:
        reply = await send_reply(services, workspace.id, email_id, data)
    except EmailNotFound:
        raise HTTPException(status_code=404, detail="Email not found") from None
    except ReplyBlocked as exc:
        raise HTTPException(status_code=409, detail=exc.reason) from None
    return _out(reply)


@router.get("")
def get_replies(
    workspace: WorkspaceDep, services: ServicesDep, email_id: EmailId
) -> list[ReplyOut]:
    try:
        return [_out(r) for r in list_replies(services, workspace.id, email_id)]
    except EmailNotFound:
        raise HTTPException(status_code=404, detail="Email not found") from None
