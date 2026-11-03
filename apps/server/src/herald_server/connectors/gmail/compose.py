"""Builds the outgoing MIME message for an owner reply."""

import base64
import re
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate, make_msgid

from herald_server.connectors.base import OutboundReply

_WHITESPACE = re.compile(r"\s+")


def _clean(value: str) -> str:
    # Header values come from customer mail (subject, address, ids). A CR or LF left in one
    # would end the header and start a new one ("Bcc: ..."), so every run of whitespace,
    # CR and LF included, becomes one space before the value is set. Do not rely on
    # email.policy to refuse it: the tests check the parsed result.
    return _WHITESPACE.sub(" ", value).strip()


def build_reply(reply: OutboundReply) -> str:
    """The reply as a base64url string without padding, the form Gmail's `raw` field takes."""
    from_address = _clean(reply.from_address)
    msg = EmailMessage(policy=SMTP)
    msg["From"] = from_address
    msg["To"] = _clean(reply.to_address)
    msg["Subject"] = _clean(reply.subject)
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=from_address.rpartition("@")[2].strip("> ") or None)
    if reply.in_reply_to:
        msg["In-Reply-To"] = _clean(reply.in_reply_to)
    if reply.references:
        # Passed as given: the caller built it from the customer's References and Message-ID.
        msg["References"] = _clean(reply.references)
    msg.set_content(reply.body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")
