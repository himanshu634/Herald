"""Connected mailboxes: lookups and status changes, the same for every provider."""

from sqlmodel import Session, select

from herald_server.bus import BusEvent
from herald_server.events import MAILBOX_STATUS, add_event, to_bus
from herald_server.models import Mailbox, MailboxStatus
from herald_server.services import Services


def get_mailbox(services: Services, mailbox_id: str) -> Mailbox | None:
    with Session(services.engine) as session:
        return session.get(Mailbox, mailbox_id)


def set_status(services: Services, mailbox_id: str, status: MailboxStatus) -> BusEvent:
    """Save the new status and its `mailbox.status` event. Publish the returned event."""
    with Session(services.engine) as session:
        mailbox = session.get(Mailbox, mailbox_id)
        if mailbox is None:
            raise LookupError(f"mailbox {mailbox_id} not found")
        mailbox.status = status
        event = add_event(
            session,
            mailbox.workspace_id,
            MAILBOX_STATUS,
            {"mailbox_id": mailbox.id, "email_address": mailbox.email_address, "status": status},
        )
        session.commit()
        session.refresh(event)
        return to_bus(event)


def active_mailbox_ids_for_address(
    services: Services, provider: str, email_address: str
) -> list[str]:
    # Cross-tenant by design: a push names only the address, and the same address may be
    # connected in several workspaces. Each of those mailboxes syncs into its own workspace.
    with Session(services.engine) as session:
        return list(
            session.exec(
                select(Mailbox.id).where(
                    Mailbox.provider == provider,
                    Mailbox.email_address == email_address.lower(),
                    Mailbox.status == MailboxStatus.ACTIVE,
                )
            ).all()
        )


def active_mailbox_ids(services: Services) -> list[str]:
    # Cross-tenant by design: the catch-up cron syncs every active mailbox in every workspace.
    with Session(services.engine) as session:
        return list(
            session.exec(select(Mailbox.id).where(Mailbox.status == MailboxStatus.ACTIVE)).all()
        )
