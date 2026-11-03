"""Tests for build_reply: the outgoing MIME message."""

import base64
import email
import email.policy

from herald_server.connectors.base import OutboundReply
from herald_server.connectors.gmail.compose import build_reply


def _reply(**kw) -> OutboundReply:
    fields = {
        "from_address": "owner@shop.in",
        "to_address": "cust@x.in",
        "subject": "Re: Where is my order",
        "body": "It ships today.",
        "in_reply_to": "<a1@x.in>",
        "references": "<z0@x.in> <a1@x.in>",
        "provider_thread_id": "t1",
    }
    return OutboundReply(**{**fields, **kw})


def _wire(raw: str) -> bytes:
    # Gmail's raw is base64url without padding.
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def _parse(raw: str):
    return email.message_from_bytes(_wire(raw), policy=email.policy.default)


def test_reply_carries_thread_headers():
    msg = _parse(build_reply(_reply()))
    assert msg["From"] == "owner@shop.in"
    assert msg["To"] == "cust@x.in"
    assert msg["Subject"] == "Re: Where is my order"
    assert msg["In-Reply-To"] == "<a1@x.in>"
    assert msg["References"] == "<z0@x.in> <a1@x.in>"
    assert msg["Message-ID"].endswith("@shop.in>")
    assert msg["Date"]


def test_header_values_cannot_add_headers():
    raw = build_reply(_reply(subject="Hi\r\nBcc: evil@x.in", to_address="a@x.in\nBcc: e@x.in"))
    msg = _parse(raw)
    assert msg["Bcc"] is None
    assert "\n" not in str(msg["Subject"]) and "\r" not in str(msg["Subject"])
    assert str(msg["Subject"]).startswith("Hi")
    assert b"\nBcc:" not in _wire(raw)


def test_body_keeps_unicode():
    msg = _parse(build_reply(_reply(body="धन्यवाद, fixed ✓")))
    assert msg.get_content_type() == "text/plain"
    assert msg.get_content().strip() == "धन्यवाद, fixed ✓"


def test_no_thread_headers_when_missing():
    msg = _parse(build_reply(_reply(in_reply_to=None, references=None)))
    assert msg["In-Reply-To"] is None
    assert msg["References"] is None
