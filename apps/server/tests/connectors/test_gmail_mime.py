"""Tests for Gmail raw-message parsing."""

import base64
from email.message import EmailMessage

from herald_server.connectors.gmail.mime import BODY_LIMIT, ParsedMessage, parse_raw_message


def _raw(msg: EmailMessage, pad: bool = True) -> str:
    encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return encoded if pad else encoded.rstrip("=")


def _msg(sender="a@b.com", subject="Hi", body="Hello") -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    if subject is not None:
        msg["Subject"] = subject
    if body is not None:
        msg.set_content(body)
    return msg


def test_plain_text_message():
    msg = _msg("Riya <Riya@Customer.in>", "Order status", "Where is my order?")
    assert parse_raw_message(_raw(msg)) == ParsedMessage(
        "riya@customer.in", "Order status", "Where is my order?"
    )


def test_multipart_alternative_prefers_plain():
    msg = _msg(body="plain version")
    msg.add_alternative("<p>html version</p>", subtype="html")
    assert parse_raw_message(_raw(msg)).body == "plain version"


def test_html_only_message_becomes_text():
    msg = EmailMessage()
    msg["From"] = "a@b.com"
    msg.set_content("<p>Where is <b>my order</b>?</p><style>p{}</style>", subtype="html")
    body = parse_raw_message(_raw(msg)).body
    assert "Where is my order?" in body
    assert "<" not in body
    assert "p{" not in body


def test_nested_multipart_mixed_with_attachment():
    msg = _msg(body="the text part")
    msg.add_attachment(b"SECRETBYTES", maintype="application", subtype="pdf", filename="a.pdf")
    body = parse_raw_message(_raw(msg)).body
    assert body == "the text part"
    assert "SECRETBYTES" not in body


def test_non_utf8_charset():
    msg = EmailMessage()
    msg["From"] = "a@b.com"
    msg.set_content("un café", charset="iso-8859-1")
    assert parse_raw_message(_raw(msg)).body == "un café"


def test_unpadded_base64url_is_accepted():
    for body in ("a", "ab", "abc", "abcd"):
        raw = _raw(_msg(body=body), pad=False)
        assert parse_raw_message(raw).body == body


def test_encoded_word_subject():
    raw = _raw(_msg()).encode()
    msg = base64.urlsafe_b64decode(raw).replace(b"Subject: Hi", b"Subject: =?UTF-8?B?Q2Fmw6k=?=")
    assert parse_raw_message(base64.urlsafe_b64encode(msg).decode()).subject == "Café"


def test_long_body_is_cut_to_limit():
    msg = _msg(body="x" * (BODY_LIMIT + 1000))
    assert len(parse_raw_message(_raw(msg)).body) == BODY_LIMIT == 50_000


def test_missing_subject_and_body():
    msg = _msg("x@y.com", subject=None, body=None)
    assert parse_raw_message(_raw(msg)) == ("x@y.com", "", "")


def test_unknown_charset_falls_back_to_utf8():
    raw = b"From: a@b.com\r\nContent-Type: text/plain; charset=bogus\r\n\r\nhello"
    assert parse_raw_message(base64.urlsafe_b64encode(raw).decode()).body == "hello"


def test_empty_plain_part_falls_back_to_html():
    msg = _msg(body="  ")
    msg.add_alternative("<p>Refund please</p>", subtype="html")
    assert parse_raw_message(_raw(msg)).body == "Refund please"


def test_newsletter_html_keeps_its_lines_without_blank_runs():
    # Shaped like a real newsletter: a title, CRLF source indentation, layout
    # tables nested several deep, and cells with no whitespace between them.
    html = (
        "<html><head><title>E-paper</title></head><body>\r\n"
        "  <table>\r\n    <tr>\r\n      <td>\r\n        Welcome to <b>E-paper</b>!\r\n"
        "      </td>\r\n    </tr>\r\n    <tr><td><table><tr><td><table><tr>"
        "<td>November 03, 2026</td><td>Tuesday</td>"
        "</tr></table></td></tr></table></td></tr>\r\n  </table>\r\n"
        "  <p>Good Morning!<br/>The latest ePaper is out.</p>\r\n"
        "  <p>Read&nbsp;more</p>\r\n</body></html>"
    )
    msg = EmailMessage()
    msg["From"] = "news@paper.in"
    msg.set_content(html, subtype="html")
    assert parse_raw_message(_raw(msg)).body == (
        "Welcome to E-paper!\n\n"
        "November 03, 2026\nTuesday\n\n"
        "Good Morning!\nThe latest ePaper is out.\n\n"
        "Read more"
    )


def test_plain_text_blank_runs_are_capped_and_indent_kept():
    msg = _msg(body="Hi,\r\n\r\n\r\n\r\nWhere is it?   \r\n  > earlier reply\r\n")
    assert parse_raw_message(_raw(msg)).body == "Hi,\n\nWhere is it?\n  > earlier reply"


def test_doubled_carriage_return_is_one_line_break():
    raw = b"From: a@b.com\r\nContent-Type: text/plain\r\n\r\nGood Morning!\r\r\nOut now."
    body = parse_raw_message(base64.urlsafe_b64encode(raw).decode()).body
    assert body == "Good Morning!\nOut now."
