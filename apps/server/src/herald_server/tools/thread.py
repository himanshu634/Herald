"""Earlier messages in the same thread as the email, oldest first."""

from herald_core.history import THREAD, Thread, ThreadIn
from herald_server.tools.bound import Bound


class ThreadTool(Bound):
    name = THREAD
    description = "Earlier messages in the same thread as this email, oldest first."
    input_model = ThreadIn
    output_model = Thread

    async def run(self, args: ThreadIn) -> Thread:
        return await self.api.thread(self.email_id, args)
