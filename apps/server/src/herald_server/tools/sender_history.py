"""Earlier emails from the same sender: counts, first seen, common topics and the latest few."""

from collections import Counter
from datetime import timedelta

from asyncer import asyncify
from sqlalchemy import func
from sqlmodel import Session, col, select

from herald_core.history import SENDER_HISTORY, PastEmail, SenderHistory, SenderHistoryIn
from herald_core.schema import Urgency
from herald_server.models import Email
from herald_server.tools.bound import Bound

MAX_SENDER_ROWS = 200


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


class SenderHistoryTool(Bound):
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
