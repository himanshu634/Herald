from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from herald_core.history import (
    RECENT_CORRECTIONS,
    SENDER_HISTORY,
    THREAD,
    CorrectionsIn,
    SenderHistoryIn,
    ThreadIn,
)
from herald_server.models import Correction, Email, Workspace
from herald_server.seed import TRIPFOLD
from herald_server.tools import build_toolbox

SENDER = "riya@customer.in"
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def _workspace(session) -> str:
    ws = Workspace(name="Tripfold", config=TRIPFOLD.model_dump(mode="json"), setup_done=True)
    session.add(ws)
    session.commit()
    return ws.id


def _email(session, ws, *, at, sender=SENDER, thread_id=None, notes=None, body="hi", **kw):
    email = Email(
        workspace_id=ws, sender=sender, subject="s", body=body, received_at=at,
        thread_id=thread_id, notes=notes, **kw,
    )  # fmt: skip
    session.add(email)
    session.commit()
    session.refresh(email)
    return email


def _before(engine, email_id) -> datetime:
    # Read back from the DB so the value is naive, like pipeline._load gives it.
    with Session(engine) as session:
        return session.get(Email, email_id).received_at


async def test_sender_history_sees_only_earlier_emails(app):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        a = _email(s, ws, at=NOW - timedelta(days=3))
        b = _email(s, ws, at=NOW - timedelta(days=1))
        later = _email(s, ws, at=NOW + timedelta(days=1))
        cur = _email(s, ws, at=NOW)
        ids = (a.id, b.id, later.id, cur.id)
    box = build_toolbox(engine, ws, ids[3], _before(engine, ids[3]))
    out = await box.call(SENDER_HISTORY, SenderHistoryIn(sender=SENDER))
    assert out.count_30d == 2 and out.count_7d == 2
    assert {e.id for e in out.recent} == {ids[0], ids[1]}
    assert out.first_seen == _before(engine, ids[0])


async def test_same_timestamp_excludes_itself(app):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        x = _email(s, ws, at=NOW)
        y = _email(s, ws, at=NOW)
        x_id, y_id = x.id, y.id
    for me, other in ((x_id, y_id), (y_id, x_id)):
        box = build_toolbox(engine, ws, me, _before(engine, me))
        out = await box.call(SENDER_HISTORY, SenderHistoryIn(sender=SENDER))
        assert [e.id for e in out.recent] == [other]


async def test_burst_counts_all_lists_five(app):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        for i in range(8):
            _email(s, ws, at=NOW - timedelta(minutes=10 + i))
        cur = _email(s, ws, at=NOW).id
    box = build_toolbox(engine, ws, cur, _before(engine, cur))
    out = await box.call(SENDER_HISTORY, SenderHistoryIn(sender="RIYA@customer.in"))
    assert out.count_7d == 8 and len(out.recent) == 5


async def test_untriaged_email_has_no_topic(app):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        _email(s, ws, at=NOW - timedelta(days=1))
        _email(s, ws, at=NOW - timedelta(days=2), notes={"topic": "refund", "urgency": "high"})
        _email(s, ws, at=NOW - timedelta(days=3), notes={"topic": "refund", "summary": "x"})
        cur = _email(s, ws, at=NOW).id
    box = build_toolbox(engine, ws, cur, _before(engine, cur))
    out = await box.call(SENDER_HISTORY, SenderHistoryIn(sender=SENDER))
    first = out.recent[0]
    assert first.topic is None and first.urgency is None and first.summary is None
    assert out.recent[1].urgency == "high" and out.recent[0].status == "new"
    assert out.top_topics == ["refund"]


async def test_thread_is_oldest_first_and_capped(app):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        ids = [
            _email(s, ws, at=NOW - timedelta(hours=10 - i), thread_id="t1", body="x" * 3000).id
            for i in range(7)
        ]
        cur = _email(s, ws, at=NOW, thread_id="t1").id
    box = build_toolbox(engine, ws, cur, _before(engine, cur))
    out = await box.call(THREAD, ThreadIn(thread_id="t1"))
    assert [m.id for m in out.messages] == ids[2:]
    assert all(len(m.body) <= 1500 for m in out.messages)


async def test_corrections_newest_first(app):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        e = _email(s, ws, at=NOW - timedelta(days=1), notes={"summary": "sum"})
        old = Correction(
            workspace_id=ws, email_id=e.id, field="route", from_value="inbox", to_value="alert",
            created_at=NOW - timedelta(days=2),
        )  # fmt: skip
        new = Correction(
            workspace_id=ws, email_id=e.id, field="route", from_value=None, to_value="closed",
            created_at=NOW - timedelta(days=1),
        )  # fmt: skip
        s.add_all([old, new])
        s.commit()
        old_id, new_id, cur = old.id, new.id, _email(s, ws, at=NOW).id
    box = build_toolbox(engine, ws, cur, _before(engine, cur))
    out = await box.call(RECENT_CORRECTIONS, CorrectionsIn())
    assert [c.id for c in out.items] == [new_id, old_id]
    assert out.items[0].summary == "sum"


async def test_tools_are_isolated(app):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws_a, ws_b = _workspace(s), _workspace(s)
        b_ids = set()
        for ws in (ws_a, ws_b):
            e = _email(s, ws, at=NOW - timedelta(days=1), thread_id="t1")
            c = Correction(
                workspace_id=ws, email_id=e.id, field="route", from_value=None, to_value="x"
            )
            s.add(c)
            s.commit()
            if ws == ws_b:
                b_ids = {e.id, c.id}
        cur = _email(s, ws_a, at=NOW, thread_id="t1").id
        a_email = s.exec(select(Email).where(Email.workspace_id == ws_a)).first().id
        b_email = s.exec(select(Email).where(Email.workspace_id == ws_b)).first().id
        # Mismatched pairs: each has one side in A and the other in B. Each join filter must
        # catch its own half.
        cross_1 = Correction(
            workspace_id=ws_a, email_id=b_email, field="route", from_value=None, to_value="x"
        )
        cross_2 = Correction(
            workspace_id=ws_b, email_id=a_email, field="route", from_value=None, to_value="x"
        )
        s.add_all([cross_1, cross_2])
        s.commit()
        b_ids |= {cross_1.id, cross_2.id}
    box = build_toolbox(engine, ws_a, cur, _before(engine, cur))
    sender = await box.call(SENDER_HISTORY, SenderHistoryIn(sender=SENDER))
    thread = await box.call(THREAD, ThreadIn(thread_id="t1"))
    corrections = await box.call(RECENT_CORRECTIONS, CorrectionsIn())
    ids = (
        {e.id for e in sender.recent}
        | {m.id for m in thread.messages}
        | {c.id for c in corrections.items}
    )
    assert ids and not ids & b_ids


async def test_corrections_skip_the_current_and_later_emails(app):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        earlier = _email(s, ws, at=NOW - timedelta(days=1))
        cur = _email(s, ws, at=NOW)
        later = _email(s, ws, at=NOW + timedelta(days=1))
        rows = [
            Correction(workspace_id=ws, email_id=e.id, field="route", from_value=None, to_value="x")
            for e in (earlier, cur, later)
        ]
        s.add_all(rows)
        s.commit()
        keep, cur_id = rows[0].id, cur.id
    box = build_toolbox(engine, ws, cur_id, _before(engine, cur_id))
    out = await box.call(RECENT_CORRECTIONS, CorrectionsIn())
    assert [c.id for c in out.items] == [keep]
