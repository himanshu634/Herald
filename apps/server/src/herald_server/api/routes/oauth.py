"""The OAuth callback: the provider sends the owner's browser back here after consent."""

import logging
from urllib.parse import urlencode

from asyncer import asyncify
from fastapi import APIRouter, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from herald_server.api.deps import QueueDep, ServicesDep
from herald_server.connectors.base import AuthRevoked, MissingRefreshToken
from herald_server.crypto import BadSecret
from herald_server.mailboxes import connect_mailbox
from herald_server.models import Workspace
from herald_server.services import Services

router = APIRouter(prefix="/api/oauth", tags=["oauth"])

log = logging.getLogger(__name__)

# How long a connect link stays usable, in seconds.
STATE_MAX_AGE = 600


def _back_to_web(services: Services, **query: str) -> RedirectResponse:
    # Always the configured web app, never a URL taken from the request or the state, so the
    # callback cannot be used as an open redirect.
    url = f"{services.settings.web_url}?{urlencode(query)}"
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _workspace_exists(services: Services, workspace_id: str) -> bool:
    with Session(services.engine) as session:
        return session.get(Workspace, workspace_id) is not None


# No ConnectorDep or SecretsDep here: they answer with JSON errors, but the owner's browser
# lands on this route, so every outcome is a redirect back to the web app.
@router.get("/{provider}/callback", status_code=status.HTTP_303_SEE_OTHER)
async def oauth_callback(
    provider: str,
    services: ServicesDep,
    queue: QueueDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    # Logs name only the outcome and ids: never the code, the state or a token.
    if error is not None:
        return _back_to_web(services, mailbox_error="access_denied")

    connector = services.connectors.get(provider)
    if connector is None or services.secrets is None:
        return _back_to_web(services, mailbox_error="provider_unavailable")

    # There is no auth yet, so the signed state is what binds the account to a workspace.
    # It is sealed with our key, so nobody can forge one that names another workspace, and it
    # expires, so a leaked connect link stops working after STATE_MAX_AGE.
    try:
        data = services.secrets.open(state or "", max_age=STATE_MAX_AGE)
    except BadSecret:
        log.info("oauth callback for %s: invalid or expired state", provider)
        return _back_to_web(services, mailbox_error="invalid_state")

    # Re-check what the state names. A state minted for one provider must not complete a
    # connect through another provider's callback. The workspace may have been deleted since
    # the link was made, and the mailbox row needs a workspace that exists.
    workspace_id = data.get("workspace_id")
    if (
        data.get("provider") != provider
        or not isinstance(workspace_id, str)
        or not await asyncify(_workspace_exists)(services, workspace_id)
    ):
        log.info("oauth callback for %s: state names another provider or no workspace", provider)
        return _back_to_web(services, mailbox_error="invalid_state")

    if not code:
        return _back_to_web(services, mailbox_error="authorization_failed")

    try:
        mailbox = await connect_mailbox(services, workspace_id, connector, code)
    except MissingRefreshToken:
        log.info("oauth callback for %s: no refresh token", provider)
        return _back_to_web(services, mailbox_error="no_refresh_token")
    except AuthRevoked:
        # An invalid, expired or reused code: the provider refuses the exchange.
        log.info("oauth callback for %s: code exchange refused", provider)
        return _back_to_web(services, mailbox_error="authorization_failed")

    # The first sync backfills recent mail; a reconnect continues from the kept cursor.
    await queue.enqueue_sync(mailbox.id)
    log.info("mailbox %s connected in workspace %s", mailbox.id, workspace_id)
    return _back_to_web(services, mailbox_connected=mailbox.id)
