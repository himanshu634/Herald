from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlmodel import Session

from herald_core.history import (
    RECENT_CORRECTIONS,
    SENDER_HISTORY,
    THREAD,
    CorrectionsIn,
    SenderHistoryIn,
    ThreadIn,
)
from herald_server.models import Correction, Email, Mailbox, Reply, ReplyStatus, Workspace
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


def _reply(session, ws, email, *, at, status=ReplyStatus.SENT, body="on it") -> Reply:
    mailbox = Mailbox(workspace_id=ws, provider="fake", email_address=f"{uuid4().hex}@shop.in")
    session.add(mailbox)
    session.commit()
    reply = Reply(
        workspace_id=ws, email_id=email.id, mailbox_id=mailbox.id, client_key=f"k{mailbox.id}",
        from_address=mailbox.email_address, to_address=email.sender, subject="Re: s", body=body,
        status=status, sent_at=at,
    )  # fmt: skip
    session.add(reply)
    session.commit()
    session.refresh(reply)
    return reply


def _before(engine, email_id) -> datetime:
    # Read back from the DB so the value is naive, like the API's scope uses it.
    with Session(engine) as session:
        return session.get(Email, email_id).received_at


async def test_sender_history_sees_only_earlier_emails(app, agent_api):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        a = _email(s, ws, at=NOW - timedelta(days=3))
        b = _email(s, ws, at=NOW - timedelta(days=1))
        later = _email(s, ws, at=NOW + timedelta(days=1))
        cur = _email(s, ws, at=NOW)
        ids = (a.id, b.id, later.id, cur.id)
    box = build_toolbox(agent_api, ids[3])
    out = await box.call(SENDER_HISTORY, SenderHistoryIn(sender=SENDER))
    assert out.count_30d == 2 and out.count_7d == 2
    assert {e.id for e in out.recent} == {ids[0], ids[1]}
    assert out.first_seen == _before(engine, ids[0])
    # decide places its 7-day repeat window from this, in the same naive time as `recent`.
    assert out.as_of == _before(engine, ids[3])


async def test_same_timestamp_excludes_itself(app, agent_api):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        x = _email(s, ws, at=NOW)
        y = _email(s, ws, at=NOW)
        x_id, y_id = x.id, y.id
    for me, other in ((x_id, y_id), (y_id, x_id)):
        box = build_toolbox(agent_api, me)
        out = await box.call(SENDER_HISTORY, SenderHistoryIn(sender=SENDER))
        assert [e.id for e in out.recent] == [other]


async def test_burst_counts_all_lists_five(app, agent_api):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        for i in range(8):
            _email(s, ws, at=NOW - timedelta(minutes=10 + i))
        cur = _email(s, ws, at=NOW).id
    box = build_toolbox(agent_api, cur)
    out = await box.call(SENDER_HISTORY, SenderHistoryIn(sender="RIYA@customer.in"))
    assert out.count_7d == 8 and len(out.recent) == 5


async def test_untriaged_email_has_no_topic(app, agent_api):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        _email(s, ws, at=NOW - timedelta(days=1))
        _email(s, ws, at=NOW - timedelta(days=2), notes={"topic": "refund", "urgency": "high"})
        _email(s, ws, at=NOW - timedelta(days=3), notes={"topic": "refund", "summary": "x"})
        cur = _email(s, ws, at=NOW).id
    box = build_toolbox(agent_api, cur)
    out = await box.call(SENDER_HISTORY, SenderHistoryIn(sender=SENDER))
    first = out.recent[0]
    assert first.topic is None and first.urgency is None and first.summary is None
    assert out.recent[1].urgency == "high" and out.recent[0].status == "new"
    assert out.top_topics == ["refund"]


async def test_thread_is_oldest_first_and_capped(app, agent_api):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        ids = [
            _email(s, ws, at=NOW - timedelta(hours=10 - i), thread_id="t1", body="x" * 3000).id
            for i in range(7)
        ]
        cur = _email(s, ws, at=NOW, thread_id="t1").id
    box = build_toolbox(agent_api, cur)
    out = await box.call(THREAD, ThreadIn(thread_id="t1"))
    assert [m.id for m in out.messages] == ids[2:]
    assert all(len(m.body) <= 1500 for m in out.messages)


async def test_thread_includes_sent_owner_replies(app, agent_api):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        first = _email(s, ws, at=NOW - timedelta(hours=3), thread_id="t1")
        reply = _reply(s, ws, first, at=NOW - timedelta(hours=2), body="Refund is on its way")
        second = _email(s, ws, at=NOW - timedelta(hours=1), thread_id="t1")
        cur = _email(s, ws, at=NOW, thread_id="t1").id
        ids = [first.id, reply.id, second.id]
        address = reply.from_address
    box = build_toolbox(agent_api, cur)
    out = await box.call(THREAD, ThreadIn(thread_id="t1"))
    assert [m.id for m in out.messages] == ids
    assert [m.from_owner for m in out.messages] == [False, True, False]
    assert out.messages[1].body == "Refund is on its way"
    assert out.messages[1].sender == address


async def test_thread_caps_after_merging_replies(app, agent_api):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        emails = [
            _email(s, ws, at=NOW - timedelta(hours=10 - 2 * i), thread_id="t1") for i in range(4)
        ]
        replies = [_reply(s, ws, e, at=e.received_at + timedelta(hours=1)) for e in emails[:3]]
        cur = _email(s, ws, at=NOW, thread_id="t1").id
        merged = [x.id for pair in zip(emails, replies, strict=False) for x in pair] + [
            emails[3].id
        ]
    box = build_toolbox(agent_api, cur)
    out = await box.call(THREAD, ThreadIn(thread_id="t1"))
    assert [m.id for m in out.messages] == merged[-5:]


async def test_thread_skips_unsent_replies(app, agent_api):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        first = _email(s, ws, at=NOW - timedelta(hours=3), thread_id="t1")
        for status in (ReplyStatus.SENDING, ReplyStatus.NOT_SENT, ReplyStatus.UNKNOWN):
            # A timestamp on purpose: only the status may keep these out.
            _reply(s, ws, first, at=NOW - timedelta(hours=2), status=status)
        cur = _email(s, ws, at=NOW, thread_id="t1").id
        first_id = first.id
    box = build_toolbox(agent_api, cur)
    out = await box.call(THREAD, ThreadIn(thread_id="t1"))
    assert [m.id for m in out.messages] == [first_id]


async def test_thread_skips_replies_after_this_email(app, agent_api):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws = _workspace(s)
        first = _email(s, ws, at=NOW - timedelta(hours=3), thread_id="t1")
        _reply(s, ws, first, at=NOW + timedelta(hours=1))
        cur = _email(s, ws, at=NOW, thread_id="t1").id
        first_id = first.id
    box = build_toolbox(agent_api, cur)
    out = await box.call(THREAD, ThreadIn(thread_id="t1"))
    assert [m.id for m in out.messages] == [first_id]


async def test_corrections_newest_first(app, agent_api):
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
    box = build_toolbox(agent_api, cur)
    out = await box.call(RECENT_CORRECTIONS, CorrectionsIn())
    assert [c.id for c in out.items] == [new_id, old_id]
    assert out.items[0].summary == "sum"


async def test_tools_are_isolated(app, agent_api):
    engine = app.state.services.engine
    with Session(engine) as s:
        ws_a, ws_b = _workspace(s), _workspace(s)
        a_ids, b_ids = set(), set()
        for ws in (ws_a, ws_b):
            e = _email(s, ws, at=NOW - timedelta(days=1), thread_id="t1")
            c = Correction(
                workspace_id=ws, email_id=e.id, field="route", from_value=None, to_value="x"
            )
            s.add(c)
            s.commit()
            r = _reply(s, ws, e, at=NOW - timedelta(hours=12))
            if ws == ws_a:
                a_reply = r.id
                a_email, a_ids = e.id, {e.id, c.id}
            else:
                b_email, b_ids = e.id, {e.id, c.id}
        cur = _email(s, ws_a, at=NOW, thread_id="t1").id
        # A reply owned by B on A's email: the Reply workspace filter must drop it.
        b_cross = _reply(s, ws_b, s.get(Email, a_email), at=NOW - timedelta(hours=11)).id
        # A reply owned by A on B's email in the same thread id: the Email filter must drop it.
        a_cross = _reply(s, ws_a, s.get(Email, b_email), at=NOW - timedelta(hours=10)).id
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
    box = build_toolbox(agent_api, cur)
    sender = await box.call(SENDER_HISTORY, SenderHistoryIn(sender=SENDER))
    thread = await box.call(THREAD, ThreadIn(thread_id="t1"))
    corrections = await box.call(RECENT_CORRECTIONS, CorrectionsIn())
    # Each tool returns exactly A's earlier email or correction, so nothing from B leaks in
    # and nothing of A's is lost. cross_2 is dropped only by the Correction.workspace_id filter.
    assert {e.id for e in sender.recent} == {a_email}
    assert {m.id for m in thread.messages} == {a_email, a_reply}
    assert not {b_cross, a_cross} & {m.id for m in thread.messages}
    assert {c.id for c in corrections.items} == a_ids - {a_email}
    assert not (a_ids | {a_email}) & b_ids


async def test_corrections_skip_the_current_and_later_emails(app, agent_api):
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
    box = build_toolbox(agent_api, cur_id)
    out = await box.call(RECENT_CORRECTIONS, CorrectionsIn())
    assert [c.id for c in out.items] == [keep]
