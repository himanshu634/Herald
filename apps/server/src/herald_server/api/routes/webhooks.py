"""Push notifications from mail providers: verify the push, then queue a sync."""

import logging

from asyncer import asyncify
from fastapi import APIRouter, HTTPException, Request, Response, status

from herald_server.api.deps import ConnectorDep, QueueDep, ServicesDep
from herald_server.connectors.base import PushIgnored, PushRejected
from herald_server.mailboxes import active_mailbox_ids_for_address

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

log = logging.getLogger(__name__)


# provider is read by ConnectorDep. The body is provider-specific, so the route takes the raw
# request and the connector parses it. Logs name only the outcome and exception types:
# never the body, headers or address.
@router.post("/{provider}", status_code=status.HTTP_204_NO_CONTENT)  # noqa: FAST003
async def receive_push(
    request: Request, connector: ConnectorDep, services: ServicesDep, queue: QueueDep
) -> Response:
    try:
        notice = await connector.parse_push(request.headers, await request.body())
    except PushRejected as exc:
        # The connector could not verify the sender: nothing is queued.
        log.info("push rejected: %s", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Push not verified") from exc
    except PushIgnored as exc:
        # Verified but not about new mail. Ack it so the provider does not retry.
        log.info("push ignored: %s", type(exc).__name__)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    mailbox_ids = await asyncify(active_mailbox_ids_for_address)(
        services, connector.provider, notice.email_address
    )
    log.info("push accepted: %d mailbox(es) queued for sync", len(mailbox_ids))
    for mailbox_id in mailbox_ids:
        await queue.enqueue_sync(mailbox_id)
    # An unknown or inactive address still gets 204: a 4xx or 5xx would make Pub/Sub retry a
    # push that can never succeed.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
