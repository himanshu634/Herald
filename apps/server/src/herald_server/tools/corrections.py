"""Times the owner overrode a triage result in this business, newest first."""

from asyncer import asyncify
from sqlmodel import Session, col, select

from herald_core.history import RECENT_CORRECTIONS, CorrectionExample, Corrections, CorrectionsIn
from herald_server.models import Correction, Email
from herald_server.tools.bound import Bound


class CorrectionsTool(Bound):
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
