from datetime import datetime

import pytest
from pydantic import ValidationError

from herald_core.history import (
    CorrectionExample,
    Corrections,
    CorrectionsIn,
    EmailContext,
    History,
    PastEmail,
    SenderHistory,
    SenderHistoryIn,
    Thread,
    ThreadIn,
    ThreadMessage,
)
from herald_core.schema import Email, Urgency

PAST = PastEmail(
    id="e1",
    received_at=datetime(2026, 10, 20, 9, 0),
    subject="Refund please",
    topic="Refunds",
    urgency=Urgency.HIGH,
    status="done",
    summary="Wants a refund.",
)
SENDER = SenderHistory(
    first_seen=datetime(2026, 10, 1, 9, 0),
    count_7d=2,
    count_30d=4,
    top_topics=["Refunds"],
    recent=[PAST],
)
MESSAGE = ThreadMessage(
    id="m1", sender="a@b.com", received_at=datetime(2026, 10, 21, 8, 0), body="Hello"
)
CORRECTION = CorrectionExample(
    id="c1",
    subject="Late bag",
    summary="Bag arrived late.",
    field="urgency",
    from_value="low",
    to_value="high",
)


def test_empty_history():
    assert History().is_empty()
    assert History(
        sender=SenderHistory(first_seen=None, count_7d=0, count_30d=0, top_topics=[], recent=[])
    ).is_empty()
    assert not History(corrections=Corrections(items=[CORRECTION])).is_empty()
    assert not History(sender=SENDER).is_empty()
    assert not History(thread=Thread(messages=[MESSAGE])).is_empty()


def test_context_from_run():
    history = History(
        sender=SENDER,
        thread=Thread(messages=[MESSAGE]),
        corrections=Corrections(items=[CORRECTION]),
    )
    asked = ["write_notes:sender_history"]
    ctx = EmailContext.from_run(history, failed=["thread"], ms={"sender_history": 4}, asked=asked)
    assert (ctx.repeat_7d, ctx.repeat_30d) == (SENDER.count_7d, SENDER.count_30d)
    assert ctx.recent_ids == [e.id for e in SENDER.recent]
    assert ctx.thread_ids == [MESSAGE.id] and ctx.correction_ids == [CORRECTION.id]
    assert ctx.failed == ["thread"] and ctx.ms == {"sender_history": 4}
    assert ctx.asked == asked


def test_context_from_empty_run():
    ctx = EmailContext.from_run(History(), failed=[], ms={})
    assert ctx == EmailContext()


def test_tool_inputs_have_no_tenant_fields():
    for model in (SenderHistoryIn, ThreadIn, CorrectionsIn):
        assert not {"workspace_id", "email_id"} & set(model.model_fields)
    with pytest.raises(ValidationError):
        CorrectionsIn(limit=5, workspace_id="other")


def test_tool_input_bounds():
    with pytest.raises(ValidationError):
        SenderHistoryIn(sender="a@b.com", days=91)
    with pytest.raises(ValidationError):
        ThreadIn(thread_id="t", limit=6)
    assert SenderHistoryIn(sender="a@b.com").limit == 5


def test_email_thread_id_is_optional():
    email = Email(id="1", workspace_id="w", sender="a@b.com", subject="s", body="b")
    assert email.thread_id is None
