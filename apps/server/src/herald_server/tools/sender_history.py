"""Earlier emails from the same sender: counts, first seen, common topics and the latest few."""

from herald_core.history import SENDER_HISTORY, SenderHistory, SenderHistoryIn
from herald_server.tools.bound import Bound


class SenderHistoryTool(Bound):
    name = SENDER_HISTORY
    description = (
        "Earlier emails from one sender in this business: how many in the last 7 and 30 days, "
        "when they first wrote, their common topics and the most recent few."
    )
    input_model = SenderHistoryIn
    output_model = SenderHistory

    async def run(self, args: SenderHistoryIn) -> SenderHistory:
        return await self.api.sender_history(self.email_id, args)
