"""Owner actions on an email's status, shared by the action routes and "Send and mark done"."""

from sqlmodel import Session

from herald_server.events import EMAIL_STATUS, add_event
from herald_server.models import Correction, Email, EmailStatus, Event

# The route decide chose, for each status the owner can send back to the inbox.
_OVERRIDDEN_ROUTE = {EmailStatus.ALERTED: "alert", EmailStatus.CLOSED: "closed"}


class WrongStatus(Exception):
    """The email is not in the status this action needs (the API answers 409)."""

    def __init__(self, previous: EmailStatus) -> None:
        super().__init__(f"Email is {previous}")
        self.previous = previous


def stage_move(
    session: Session,
    workspace_id: str,
    email: Email,
    to: EmailStatus,
    only_from: EmailStatus | None = None,
) -> Event:
    """Owner action: the only way, besides the decide step, that an email's status changes.

    Stages the new status, its `email.status` event and any correction in the caller's
    session. The caller commits, then publishes the event. `email` must have been loaded
    filtered by `workspace_id`. Raises `WrongStatus` when `only_from` is set and not met.
    """
    previous = email.status
    if only_from is not None and previous is not only_from:
        raise WrongStatus(previous)
    email.status = to
    event = add_event(
        session, workspace_id, EMAIL_STATUS, {"email_id": email.id, "from": previous, "to": to}
    )
    # The owner overrode the decide step. Saved so the model sees it on later emails.
    overridden = _OVERRIDDEN_ROUTE.get(previous) if to is EmailStatus.INBOX else None
    if overridden is not None:
        session.add(
            Correction(
                workspace_id=workspace_id,
                email_id=email.id,
                field="route",
                from_value=overridden,
                to_value="inbox",
            )
        )
    return event
