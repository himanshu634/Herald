"""POST /api/webhooks/{provider}: verified pushes queue a sync for matching mailboxes."""

import json

from test_mailboxes_api import connect, demo_workspace, emails_of, message

from herald_server.connectors.base import FetchResult

OK = {"x-fake-auth": "ok"}


def push(client, email: str = "owner@shop.in", headers=OK, provider: str = "fake"):
    return client.post(
        f"/api/webhooks/{provider}", content=json.dumps({"email": email}), headers=headers
    )


async def test_push_queues_sync_for_matching_mailbox(app, client, fake_connector):
    ws = await demo_workspace(client)
    await connect(app, client, ws)
    fake_connector.queue = [message("m1")]

    response = await push(client, "Owner@Shop.in")
    await app.state.queue.drain()

    assert response.status_code == 204
    assert len(emails_of(app, ws)) == 1


async def test_push_without_auth_is_401(app, client, fake_connector):
    ws = await demo_workspace(client)
    await connect(app, client, ws)
    fake_connector.queue = [message("m1")]

    response = await push(client, headers={})
    await app.state.queue.drain()

    assert response.status_code == 401
    assert emails_of(app, ws) == []


async def test_push_for_unknown_address_is_acked(app, client, fake_connector):
    ws = await demo_workspace(client)
    await connect(app, client, ws)
    fake_connector.queue = [message("m1")]

    response = await push(client, "stranger@elsewhere.in")
    await app.state.queue.drain()

    assert response.status_code == 204
    assert emails_of(app, ws) == []


async def test_push_for_unusable_body_is_acked(client, fake_connector):
    response = await client.post("/api/webhooks/fake", content=b"nope", headers=OK)

    assert response.status_code == 204


async def test_push_for_paused_mailbox_is_acked_without_sync(app, client, fake_connector):
    ws = await demo_workspace(client)
    mailbox_id = await connect(app, client, ws)
    await client.post(f"/api/workspaces/{ws}/mailboxes/{mailbox_id}/pause")
    fake_connector.queue = [message("m1")]

    response = await push(client)
    await app.state.queue.drain()

    assert response.status_code == 204
    assert emails_of(app, ws) == []


async def test_push_syncs_every_workspace_with_that_address(app, client, fake_connector):
    ws_a = await demo_workspace(client)
    ws_b = await demo_workspace(client)
    await connect(app, client, ws_a)
    await connect(app, client, ws_b)

    async def fetch_changes(credentials, cursor) -> FetchResult:
        # Every mailbox gets its own copy of the new message, as a real provider would give.
        return FetchResult(messages=[message("m1")], cursor="1")

    fake_connector.fetch_changes = fetch_changes

    response = await push(client)
    await app.state.queue.drain()

    assert response.status_code == 204
    assert len(emails_of(app, ws_a)) == 1
    assert len(emails_of(app, ws_b)) == 1


async def test_push_to_unknown_provider_is_404(client):
    response = await push(client, provider="nope")

    assert response.status_code == 404
    assert response.json()["detail"] == "Mail provider not available"
