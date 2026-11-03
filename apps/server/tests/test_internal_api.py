"""The internal routes the pipeline uses: token, scope, contract and retry-safe failures."""

import httpx
import pytest
from arq import Retry
from pydantic import SecretStr
from sqlmodel import Session, col, select

from herald_core.history import CorrectionsIn, EmailContext, SenderHistoryIn
from herald_core.schema import Decision, Route
from herald_server.events import ALERT_SENT, EMAIL_NOTED
from herald_server.internal.client import AgentApi, ApiUnavailable
from herald_server.internal.schemas import TriageResult
from herald_server.internal.token import TOKEN_HEADER, internal_token
from herald_server.models import Email, Event, Workspace
from herald_server.seed import TRIPFOLD
from herald_server.worker.main import process_email_job

PREFIX = "/internal/v1/emails"


def _email(app) -> str:
    with Session(app.state.services.engine) as session:
        ws = Workspace(name="Tripfold", config=TRIPFOLD.model_dump(mode="json"), setup_done=True)
        session.add(ws)
        session.commit()
        email = Email(workspace_id=ws.id, sender="a@b.in", subject="Card", body="Someone used it")
        session.add(email)
        session.commit()
        return email.id


async def test_internal_routes_need_the_token(app, client):
    email_id = _email(app)
    url = f"{PREFIX}/{email_id}/triage-input"
    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers={TOKEN_HEADER: "wrong"})).status_code == 401
    good = await client.get(url, headers={TOKEN_HEADER: app.state.internal_token})
    assert good.status_code == 200
    assert good.json()["email"]["id"] == email_id


async def test_internal_routes_are_not_in_the_public_schema(app):
    assert not [path for path in app.openapi()["paths"] if path.startswith("/internal")]


async def test_unknown_email_is_404(agent_api):
    with pytest.raises(httpx.HTTPStatusError) as raised:
        await agent_api.triage_input("nope")
    assert raised.value.response.status_code == 404


async def test_a_caller_cannot_name_a_workspace(app, client):
    # Tool inputs forbid extra fields, so the scope can only come from the email's own row.
    email_id = _email(app)
    response = await client.get(
        f"{PREFIX}/{email_id}/history/corrections",
        params={"limit": 5, "workspace_id": "other"},
        headers={TOKEN_HEADER: app.state.internal_token},
    )
    assert response.status_code == 422


async def test_save_sets_status_and_records_alert_after_note(app, agent_api):
    email_id = _email(app)
    decision = Decision(route=Route.ALERT, urgency=None, reason="safety floor: fraud")
    await agent_api.save_triage_result(
        email_id, TriageResult(notes=None, decision=decision, context=EmailContext())
    )
    with Session(app.state.services.engine) as session:
        email = session.get(Email, email_id)
        events = session.exec(select(Event).order_by(col(Event.id))).all()
    assert email.status == "alerted"
    assert [e.type for e in events] == [EMAIL_NOTED, ALERT_SENT]
    assert events[1].data["summary"] == "Card"


def test_token_is_required_for_the_arq_queue(settings):
    arq = settings.model_copy(update={"queue": "arq"})
    with pytest.raises(RuntimeError, match="HERALD_INTERNAL_TOKEN"):
        internal_token(arq, allow_random=False)
    short = arq.model_copy(update={"internal_token": SecretStr("short")})
    with pytest.raises(RuntimeError, match="at least"):
        internal_token(short, allow_random=False)
    assert internal_token(settings, allow_random=True) != internal_token(
        settings, allow_random=True
    )


def _api(handler) -> AgentApi:
    return AgentApi(httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://x"))


async def test_reads_retry_on_any_network_failure_or_5xx():
    def down(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ApiUnavailable):
        await _api(down).corrections("e1", CorrectionsIn())
    with pytest.raises(ApiUnavailable):
        await _api(lambda request: httpx.Response(503)).sender_history(
            "e1", SenderHistoryIn(sender="a@b.in")
        )


async def test_save_retries_only_when_the_request_never_arrived():
    result = TriageResult(
        notes=None, decision=Decision(route=Route.INBOX, urgency=None, reason="x"),
        context=EmailContext(),
    )  # fmt: skip

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    def lost(request):
        # The API may have committed before the answer was lost: retrying would publish twice.
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ApiUnavailable):
        await _api(refused).save_triage_result("e1", result)
    with pytest.raises(httpx.ReadTimeout):
        await _api(lost).save_triage_result("e1", result)


async def test_worker_retries_triage_while_the_api_is_down(app):
    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    ctx = {"agent_api": _api(refused), "services": app.state.services, "job_try": 2}
    with pytest.raises(Retry) as raised:
        await process_email_job(ctx, "e1")
    assert raised.value.defer_score == 10_000
