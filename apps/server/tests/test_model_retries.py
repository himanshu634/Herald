"""The worker tries an email again when the AI was down, and saves on its last try."""

import pytest
from arq import Retry
from test_api import demo_workspace, send

from herald_core.graph import build_graph
from herald_core.model import FakeModel, ModelError
from herald_core.schema import FailureKind
from herald_server.worker import main as worker_main
from herald_server.worker.main import (
    MODEL_RETRY_CAP,
    PROCESS_EMAIL_TRIES,
    model_retry_defer,
    process_email_job,
)


class DownModel(FakeModel):
    async def write_notes(self, email, business_name, config, history=None, tools=()):
        raise ModelError("overloaded", FailureKind.UNAVAILABLE)

    async def judge_rules(self, email, business_name, config, history=None, tools=()):
        raise ModelError("overloaded", FailureKind.UNAVAILABLE)


@pytest.fixture
def ai_down(app, monkeypatch):
    monkeypatch.setattr(app.state.services, "graph", build_graph(DownModel()))


@pytest.fixture
def saved(agent_api, monkeypatch) -> list:
    results = []
    real_save = agent_api.save_triage_result

    async def spy(email_id, result):
        results.append(result)
        return await real_save(email_id, result)

    monkeypatch.setattr(agent_api, "save_triage_result", spy)
    return results


def ctx(app, agent_api, job_try: int) -> dict:
    return {"services": app.state.services, "agent_api": agent_api, "job_try": job_try}


async def test_ai_down_retries_the_job_and_saves_nothing(app, client, agent_api, ai_down, saved):
    email = await send(app, client, await demo_workspace(client), "Order", "Where is my bag?")
    with pytest.raises(Retry) as raised:
        await process_email_job(ctx(app, agent_api, job_try=1), email["id"])
    assert 24_000 <= raised.value.defer_score <= 36_000
    assert saved == []


async def test_last_try_saves_needs_a_look_with_the_reason(app, client, agent_api, ai_down, saved):
    ws = await demo_workspace(client)
    email = await send(app, client, ws, "Order", "Where is my bag?")
    route = await process_email_job(ctx(app, agent_api, PROCESS_EMAIL_TRIES), email["id"])
    assert route == "needs_a_look"
    [result] = saved
    assert result.decision.reason == "The AI was unavailable"
    detail = (await client.get(f"/api/workspaces/{ws}/emails/{email['id']}")).json()
    assert {f["kind"] for f in detail["context"]["ai_failures"]} == {"unavailable"}


async def test_floor_alert_is_saved_on_the_first_try(app, client, agent_api, ai_down, saved):
    ws = await demo_workspace(client)
    email = await send(app, client, ws, "Refund", "Refund me or I will take legal action.")
    route = await process_email_job(ctx(app, agent_api, job_try=1), email["id"])
    assert route == "alert"
    assert len(saved) == 1


async def test_try_tells_the_owner_to_try_again(app, client, ai_down):
    ws = await demo_workspace(client)
    email = await send(app, client, ws, "Order", "Where is my bag?")
    config = (await client.get(f"/api/workspaces/{ws}")).json()["config"]
    tried = await client.post(
        f"/api/workspaces/{ws}/emails/{email['id']}/try", json={"config": config}
    )
    assert tried.status_code == 503
    assert tried.json()["detail"] == "ai_unavailable"


def test_retry_waits_double_each_try_with_jitter(monkeypatch):
    monkeypatch.setattr(worker_main.random, "uniform", lambda low, high: 1.0)
    assert [model_retry_defer(n, None) for n in range(1, 6)] == [30, 60, 120, 240, 480]
    assert model_retry_defer(9, None) == MODEL_RETRY_CAP


def test_retry_honours_retry_after_up_to_the_cap(monkeypatch):
    monkeypatch.setattr(worker_main.random, "uniform", lambda low, high: 1.0)
    assert model_retry_defer(1, 100) == 100
    assert model_retry_defer(1, 10_000) == MODEL_RETRY_CAP
