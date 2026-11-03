"""Read-only history tools. Each query is scoped to the workspace bound at construction."""

from collections import Counter
from datetime import datetime, timedelta

from asyncer import asyncify
from sqlalchemy import Engine, func
from sqlmodel import Session, col, select

from herald_core.history import (
    RECENT_CORRECTIONS,
    SENDER_HISTORY,
    THREAD,
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
from herald_server.models import Correction, Email

MAX_SENDER_ROWS = 200
MAX_BODY_CHARS = 1500


class _Bound:
    """The scope every query shares. The model never supplies any of these values."""

    def __init__(self, engine: Engine, workspace_id: str, email_id: str, before: datetime) -> None:
        self.engine = engine
        self.workspace_id = workspace_id
        self.email_id = email_id
        self.before = before

    def _scope(self) -> tuple:
        # Same workspace, never the email being judged (compared by id, since two emails can
        # share a timestamp), and nothing received after it. `<=` plus the id check means two
        # emails with equal timestamps each see the other but never themselves.
        return (
            Email.workspace_id == self.workspace_id,
            Email.id != self.email_id,
            Email.received_at <= self.before,
        )

    def earlier_emails(self):
        return select(Email).where(*self._scope())


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


class SenderHistoryTool(_Bound):
    name = SENDER_HISTORY
    description = (
        "Earlier emails from one sender in this business: how many in the last 7 and 30 days, "
        "when they first wrote, their common topics and the most recent few."
    )
    input_model = SenderHistoryIn
    output_model = SenderHistory

    async def run(self, args: SenderHistoryIn) -> SenderHistory:
        return await asyncify(self._query)(args)

    def _query(self, args: SenderHistoryIn) -> SenderHistory:
        sender = args.sender.lower()  # senders are stored lowercased
        mine = self.earlier_emails().where(Email.sender == sender)
        with Session(self.engine) as session:
            rows = session.exec(
                mine.where(Email.received_at >= self.before - timedelta(days=args.days))
                .order_by(col(Email.received_at).desc(), col(Email.id))
                .limit(MAX_SENDER_ROWS)
            ).all()
            # Not limited to the window: "first seen" is the sender's oldest earlier email.
            first_seen = session.exec(
                select(func.min(Email.received_at)).where(*self._scope(), Email.sender == sender)
            ).one()
        week_start = self.before - timedelta(days=7)
        month_start = self.before - timedelta(days=30)
        topics = Counter(topic for row in rows if row.notes and (topic := row.notes.get("topic")))
        return SenderHistory(
            first_seen=first_seen,
            as_of=self.before,
            count_7d=sum(1 for row in rows if row.received_at >= week_start),
            count_30d=sum(1 for row in rows if row.received_at >= month_start),
            top_topics=[topic for topic, _ in topics.most_common(3)],
            recent=[_past_email(row) for row in rows[: args.limit]],
        )


class ThreadTool(_Bound):
    name = THREAD
    description = "Earlier messages in the same thread as this email, oldest first."
    input_model = ThreadIn
    output_model = Thread

    async def run(self, args: ThreadIn) -> Thread:
        return await asyncify(self._query)(args)

    def _query(self, args: ThreadIn) -> Thread:
        with Session(self.engine) as session:
            rows = session.exec(
                self.earlier_emails()
                .where(Email.thread_id == args.thread_id)
                .order_by(col(Email.received_at).desc(), col(Email.id))
                .limit(args.limit)
            ).all()
        # Newest few were fetched; the model reads them in conversation order.
        return Thread(
            messages=[
                ThreadMessage(
                    id=row.id,
                    sender=row.sender,
                    received_at=row.received_at,
                    body=row.body[:MAX_BODY_CHARS],
                )
                for row in reversed(rows)
            ]
        )


class CorrectionsTool(_Bound):
    name = RECENT_CORRECTIONS
    description = "Times the owner overrode a triage result for this business, newest first."
    input_model = CorrectionsIn
    output_model = Corrections

    async def run(self, args: CorrectionsIn) -> Corrections:
        return await asyncify(self._query)(args)

    def _query(self, args: CorrectionsIn) -> Corrections:
        with Session(self.engine) as session:
            # Both rows must be in the bound workspace (the Email side comes from the shared
            # scope), so a bad email_id cannot leak a subject or summary from another tenant.
            # The scope also drops corrections on the current email and on later ones.
            rows = session.exec(
                select(Correction, Email)
                .join(Email, col(Email.id) == col(Correction.email_id))
                .where(
                    Correction.workspace_id == self.workspace_id,
                    *self._scope(),
                )
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
