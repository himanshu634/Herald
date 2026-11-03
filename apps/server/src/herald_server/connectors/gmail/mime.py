"""Turn Gmail's base64url `raw` message into sender, subject and plain-text body."""

import base64
import email
import email.policy
import re
from email.utils import getaddresses, parseaddr
from html.parser import HTMLParser
from typing import NamedTuple

BODY_LIMIT = 50_000
# RFC 5322 caps a header line at 998 characters.
MESSAGE_ID_LIMIT = 998
# A reply carries the thread's ids in References. RFC 5322 3.6.4 lets a sender trim the oldest,
# and Gmail threads on the newest, so a long thread cannot make the header too long.
REFERENCES_KEEP = 20


class ParsedMessage(NamedTuple):
    sender: str
    subject: str
    body: str
    message_id: str | None = None
    references: str | None = None
    reply_to: str | None = None


# Tags that end a line, and tags that end a paragraph (a blank line after).
_LINE_TAGS = {"div", "tr", "td", "th", "li", "dt", "dd", "section", "article", "header", "footer"}
_PARAGRAPH_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "blockquote"}
_SKIP_TAGS = {"script", "style", "title"}
_SPACE_RUN = re.compile(r"\s+")
_BLANK_RUN = re.compile(r"\n{3,}")
# Mail re-encoded more than once can end lines with "\r\r\n"; that is one break.
_LINE_END = re.compile(r"\r*\n|\r")


class _TextExtractor(HTMLParser):
    """Reads HTML the way a browser lays it out, as text.

    Whitespace in the source is collapsed to one space, as a browser does, and
    block tags break lines. Newsletters nest layout tables many levels deep, so
    a block tag only asks for a break and the break is written once, before the
    next text. Writing a newline per tag would leave runs of blank lines.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self._pending = 0  # 0 none, 1 new line, 2 blank line

    def _break(self, level: int) -> None:
        self._pending = max(self._pending, level)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in ("br", "hr"):
            # The default handle_startendtag calls both start and end handlers,
            # so <br/> is handled here only, or it would break twice.
            self.parts.append("\n")
            self._pending = 0
        elif tag in _PARAGRAPH_TAGS:
            self._break(2)
        elif tag in _LINE_TAGS:
            self._break(1)

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if self._skip:
                self._skip -= 1
        elif tag in _PARAGRAPH_TAGS:
            self._break(2)
        elif tag in _LINE_TAGS:
            self._break(1)

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = _SPACE_RUN.sub(" ", data)
        if not text.strip():
            # Whitespace between tags only separates words on the same line.
            if self.parts and not self._pending and not self.parts[-1].endswith((" ", "\n")):
                self.parts.append(" ")
            return
        if self._pending:
            if self.parts:
                self.parts.append("\n" * self._pending)
            self._pending = 0
            text = text.lstrip()
        elif not self.parts or self.parts[-1].endswith("\n"):
            text = text.lstrip()
        self.parts.append(text)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return _tidy("".join(parser.parts))


def _tidy(text: str) -> str:
    """Normalise line endings, drop trailing spaces and cap blank lines at one.

    Leading spaces stay: quoted replies in plain-text mail use them.
    """
    text = _LINE_END.sub("\n", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return _BLANK_RUN.sub("\n\n", text).strip()


def parse_raw_message(raw: str) -> ParsedMessage:
    # Gmail omits base64 padding; urlsafe_b64decode raises on a length that is
    # not a multiple of 4, so restore it first.
    data = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    msg = email.message_from_bytes(data, policy=email.policy.default)

    sender = parseaddr(str(msg.get("From", "")))[1].lower()
    subject = str(msg.get("Subject", ""))

    body = _body_text(msg, ("plain", "html"))
    if not body:
        # An empty text/plain part must not hide a populated text/html alternative.
        body = _body_text(msg, ("html",))
    return ParsedMessage(
        sender,
        subject,
        body[:BODY_LIMIT],
        message_id=_header(msg, "Message-ID", MESSAGE_ID_LIMIT),
        references=_references(msg),
        reply_to=_reply_to(msg),
    )


def _header(msg: email.message.Message, name: str, limit: int | None = None) -> str | None:
    """One header value on a single line, or None.

    The value comes from outside mail. Folding every whitespace run, CR and LF included, to a
    space means it can never carry a line break into a header we send. A break there would let
    a sender inject extra headers into the owner's reply.
    """
    value = _SPACE_RUN.sub(" ", str(msg.get(name, ""))).strip()
    return value[:limit] or None


def _references(msg: email.message.Message) -> str | None:
    value = _header(msg, "References")
    if value is None:
        return None
    return " ".join(value.split(" ")[-REFERENCES_KEEP:])


def _reply_to(msg: email.message.Message) -> str | None:
    """The first Reply-To address, lower-case. A contact form sets it to the customer."""
    value = _header(msg, "Reply-To")
    if value is None:
        return None
    for _name, address in getaddresses([value]):
        if address:
            return address.lower()
    return None


def _body_text(msg: email.message.Message, preference: tuple[str, ...]) -> str:
    part = msg.get_body(preferencelist=preference)
    if part is None:
        return ""
    try:
        content = part.get_content()
    except LookupError:
        # Untrusted mail can name a charset Python does not know; decode as UTF-8
        # instead of letting one bad message abort the caller.
        payload = part.get_payload(decode=True)
        content = payload.decode("utf-8", errors="replace") if payload else ""
    # Only reduce to text when we fell back to HTML. A plain part is used as is,
    # because stripping "tags" from plain text would eat literal "<...>" content.
    if part.get_content_type() == "text/html":
        return _html_to_text(content)
    return _tidy(content)
