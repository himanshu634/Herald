"""Earlier messages in the same thread as the email, oldest first."""

from asyncer import asyncify
from sqlmodel import Session, col

from herald_core.history import THREAD, Thread, ThreadIn, ThreadMessage
from herald_server.models import Email
from herald_server.tools.bound import Bound

MAX_BODY_CHARS = 1500


class ThreadTool(Bound):
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
