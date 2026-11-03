"""Times the owner overrode a triage result in this business, newest first."""

from herald_core.history import RECENT_CORRECTIONS, Corrections, CorrectionsIn
from herald_server.tools.bound import Bound


class CorrectionsTool(Bound):
    name = RECENT_CORRECTIONS
    description = "Times the owner overrode a triage result for this business, newest first."
    input_model = CorrectionsIn
    output_model = Corrections

    async def run(self, args: CorrectionsIn) -> Corrections:
        return await self.api.corrections(self.email_id, args)
