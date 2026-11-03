"""Turn Gmail's base64url `raw` message into sender, subject and plain-text body."""

import base64
import email
import email.policy
from email.utils import parseaddr
from html.parser import HTMLParser
from typing import NamedTuple

BODY_LIMIT = 50_000


class ParsedMessage(NamedTuple):
    sender: str
    subject: str
    body: str


class _TextExtractor(HTMLParser):
    """Collects text nodes, ignoring tags and the content of script and style."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return "".join(parser.parts).strip()


def parse_raw_message(raw: str) -> ParsedMessage:
    # Gmail omits base64 padding; urlsafe_b64decode raises on a length that is
    # not a multiple of 4, so restore it first.
    data = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    msg = email.message_from_bytes(data, policy=email.policy.default)

    sender = parseaddr(str(msg.get("From", "")))[1].lower()
    subject = str(msg.get("Subject", ""))

    part = msg.get_body(preferencelist=("plain", "html"))
    body = ""
    if part is not None:
        content = part.get_content()
        # Only reduce to text when we fell back to HTML. A plain part is used as is,
        # because stripping "tags" from plain text would eat literal "<...>" content.
        body = _html_to_text(content) if part.get_content_type() == "text/html" else content
        body = body.strip()  # drop the newline mail clients append
    return ParsedMessage(sender, subject, body[:BODY_LIMIT])
