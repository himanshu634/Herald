"""The history queries behind the agent's tools. Each is read-only and stays in one workspace."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlmodel import Session, col, select

from herald_core.history import (
    CorrectionExample,
    Corrections,
    CorrectionsIn,
    PastEmail,
    SenderHistory,
    SenderHistoryIn,
    Thread,
    ThreadIn,
    ThreadMessage,
)
from herald_core.schema import Urgency
from herald_server.models import Correction, Email, Reply, ReplyStatus

MAX_SENDER_ROWS = 200
MAX_BODY_CHARS = 1500


@dataclass(frozen=True)
class Scope:
    """The email being judged. Every value comes from its row, never from the caller."""

    workspace_id: str
    email_id: str
    before: datetime

    @classmethod
    def of(cls, email: Email) -> "Scope":
        # received_at is the row's own (naive) value, the same way every query compares it.
        return cls(email.workspace_id, email.id, email.received_at)

    def where(self) -> tuple:
        # Same workspace, never the email being judged (compared by id, since two emails can
        # share a timestamp), and nothing received after it. `<=` plus the id check means two
        # emails with equal timestamps each see the other but never themselves.
        return (
            Email.workspace_id == self.workspace_id,
            Email.id != self.email_id,
            Email.received_at <= self.before,
        )

    def earlier_emails(self):
        return select(Email).where(*self.where())


def _past_email(email: Email) -> PastEmail:
    notes = email.notes or {}
    urgency = notes.get("urgency")
    return PastEmail(
        id=email.id,
        received_at=email.received_at,
        subject=email.subject,
        topic=notes.get("topic"),
        urgency=Urgency(urgency) if urgency else None,
        status=email.status.value,
        summary=notes.get("summary"),
    )


def sender_history(session: Session, scope: Scope, args: SenderHistoryIn) -> SenderHistory:
    sender = args.sender.lower()  # senders are stored lowercased
    mine = scope.earlier_emails().where(Email.sender == sender)
    rows = session.exec(
        mine.where(Email.received_at >= scope.before - timedelta(days=args.days))
        .order_by(col(Email.received_at).desc(), col(Email.id))
        .limit(MAX_SENDER_ROWS)
    ).all()
    # Not limited to the window: "first seen" is the sender's oldest earlier email.
    first_seen = session.exec(
        select(func.min(Email.received_at)).where(*scope.where(), Email.sender == sender)
    ).one()
    week_start = scope.before - timedelta(days=7)
    month_start = scope.before - timedelta(days=30)
    topics = Counter(topic for row in rows if row.notes and (topic := row.notes.get("topic")))
    return SenderHistory(
        first_seen=first_seen,
        as_of=scope.before,
        count_7d=sum(1 for row in rows if row.received_at >= week_start),
        count_30d=sum(1 for row in rows if row.received_at >= month_start),
        top_topics=[topic for topic, _ in topics.most_common(3)],
        recent=[_past_email(row) for row in rows[: args.limit]],
    )


def thread(session: Session, scope: Scope, args: ThreadIn) -> Thread:
    emails = session.exec(
        scope.earlier_emails()
        .where(Email.thread_id == args.thread_id)
        .order_by(col(Email.received_at).desc(), col(Email.id))
        .limit(args.limit)
    ).all()
    # Only SENT replies: a sending, failed or unknown one may never have reached the customer,
    # and the model must not treat it as something they were told. The cutoff is strict, so a
    # reply sent after this email arrived is never shown. Both rows must be in the scope's
    # workspace, as for corrections.
    replies = session.exec(
        select(Reply)
        .join(Email, col(Email.id) == col(Reply.email_id))
        .where(
            Reply.workspace_id == scope.workspace_id,
            Email.workspace_id == scope.workspace_id,
            Email.thread_id == args.thread_id,
            Reply.status == ReplyStatus.SENT,
            col(Reply.sent_at) < scope.before,
        )
        .order_by(col(Reply.sent_at).desc(), col(Reply.id))
        .limit(args.limit)
    ).all()
    # Each list holds its own newest `limit` rows. Merge by time and cap again: the newest
    # `limit` of the union are all inside these two lists, so none is lost. Capping each list
    # alone would show up to twice the limit. Then flip to conversation order.
    merged = [
        ThreadMessage(
            id=row.id,
            sender=row.sender,
            received_at=row.received_at,
            body=row.body[:MAX_BODY_CHARS],
        )
        for row in emails
    ] + [
        ThreadMessage(
            id=reply.id,
            sender=reply.from_address,
            received_at=reply.sent_at,
            body=reply.body[:MAX_BODY_CHARS],
            from_owner=True,
        )
        for reply in replies
        if reply.sent_at is not None
    ]
    # Newest first, ties by id, matching the per-list order. Sorting the id first and then the
    # time (stable) avoids negating a datetime.
    merged.sort(key=lambda m: m.id)
    merged.sort(key=lambda m: m.received_at, reverse=True)
    return Thread(messages=merged[: args.limit][::-1])


def corrections(session: Session, scope: Scope, args: CorrectionsIn) -> Corrections:
    # Both rows must be in the scope's workspace (the Email side comes from the shared scope),
    # so a bad email_id cannot leak a subject or summary from another tenant. The scope also
    # drops corrections on the current email and on later ones.
    rows = session.exec(
        select(Correction, Email)
        .join(Email, col(Email.id) == col(Correction.email_id))
        .where(Correction.workspace_id == scope.workspace_id, *scope.where())
        .order_by(col(Correction.created_at).desc(), col(Correction.id))
        .limit(args.limit)
    ).all()
    return Corrections(
        items=[
            CorrectionExample(
                id=correction.id,
                subject=email.subject,
                summary=(email.notes or {}).get("summary"),
                field=correction.field,
                from_value=correction.from_value,
                to_value=correction.to_value,
            )
            for correction, email in rows
        ]
    )
