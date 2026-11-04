"""The prompt Claude reads for each email.

The fixed instructions come from triage.md; the business block is built from the
workspace's config.
"""

import re
from importlib.resources import files

from herald_core.history import History, SenderHistory
from herald_core.schema import Email, WorkspaceConfig

# Read once so every call sends the same bytes and the prompt cache stays warm.
TRIAGE_INSTRUCTIONS = (
    files("herald_core").joinpath("prompts/triage.md").read_text(encoding="utf-8").rstrip()
)


def _line(text: str) -> str:
    # One line per item: a newline in an owner's text must not start a fake section.
    return " ".join(text.split())


def business_block(name: str, config: WorkspaceConfig) -> str:
    # The order is part of the prompt cache key, so it must not depend on the data.
    sections = [f"Name: {_line(name)}", f"Profile:\n{config.business_profile}"]
    topics = [
        f"- {_line(t.name)}: {_line(t.meaning)}" if t.meaning else f"- {_line(t.name)}"
        for t in config.topics
    ]
    facts = [f"- {_line(fact)}" for fact in config.facts]
    guidance = [f"- {_line(line)}" for line in config.guidance]
    # Only the rule's id and condition: Claude must not know the name or what it triggers.
    rules = [f"- id={rule.id}: {_line(rule.when)}" for rule in config.rules]
    for heading, items in (
        ("Topics", topics),
        ("Facts", facts),
        ("Guidance", guidance),
        ("Rules", rules),
    ):
        if items:
            sections.append(f"{heading}:\n" + "\n".join(items))
    return "<business>\n" + "\n\n".join(sections) + "\n</business>"


def system_prompt(name: str, config: WorkspaceConfig) -> str:
    return TRIAGE_INSTRUCTIONS + "\n\n" + business_block(name, config)


def email_block(email: Email, important: bool) -> str:
    # Header fields are one line each: a newline must not forge a line like "From: ...".
    sender = _line(email.sender)
    sender = f"{sender} (important contact)" if important else sender
    subject = _strip(_HISTORY_TAG, _line(email.subject))
    body = _strip(_HISTORY_TAG, email.body)
    return f"<email>\nFrom: {sender}\nSubject: {subject}\n\n{body}\n</email>"


# The current email can also forge a history block (a fake "owner corrections" section that
# would steer the model), so <history> tags are removed from it too. <email> and <business>
# are left alone here on purpose.
_HISTORY_TAG = re.compile(r"<\s*/?\s*history\b[^>]*>", re.I)

# History is the only other part of the prompt built from other people's text (earlier emails and
# their bodies). Tags that match our own fences are removed so none of it can close
# <history> early or open a fake <email>, <business> or <message> block.
_FENCE_TAG = re.compile(r"<\s*/?\s*(history|message|email|business)\b[^>]*>", re.I)


def _strip(pattern: re.Pattern[str], text: str) -> str:
    # One pass can rebuild a tag: "<<history>/history>" becomes "</history>". Repeat until
    # the text stops changing.
    while (cleaned := pattern.sub("", text)) != text:
        text = cleaned
    return text


def _clean(text: str) -> str:
    return _strip(_FENCE_TAG, text)


def _day(when) -> str:
    return when.strftime("%Y-%m-%d")


def sender_history_text(sender: SenderHistory) -> str:
    """What the sender_history tool answers. The earlier emails are other people's text, so they
    get the same cleaning and <history> fence as the history block."""
    if sender.first_seen is None:
        return "No earlier emails from this sender."
    lines = [
        f"Sender: first seen {_day(sender.first_seen)}. {sender.count_7d} earlier emails "
        f"in the last 7 days, {sender.count_30d} in the last 30."
    ]
    if sender.top_topics:
        topics = ", ".join(_clean(_line(t)) for t in sender.top_topics)
        lines.append(f"Usual topics: {topics}.")
    if sender.recent:
        lines.append("Recent emails from this sender, newest first:")
        for past in sender.recent:
            # An email not triaged yet has no topic, urgency or summary: leave them out.
            parts = [
                _day(past.received_at),
                past.topic,
                past.urgency.value if past.urgency else None,
                past.status,
                past.summary or past.subject,
            ]
            lines.append("- " + " · ".join(_clean(_line(p)) for p in parts if p))
    return "<history>\n" + "\n".join(lines) + "\n</history>"


def history_block(history: History) -> str:
    """The fenced <history> block, or "" when there is nothing to show.

    The sender's history is not here: the model asks for it with the sender_history tool.
    """
    sections: list[str] = []
    if history.thread and history.thread.messages:
        messages = []
        for m in history.thread.messages:
            # A quote in the sender would end the attribute and let the text add its own.
            # Drop quotes first: removing them after cleaning could rebuild a tag.
            # The owner's own messages read "the owner": a bare mailbox address means nothing to
            # the model. The fixed label also keeps the address out of the prompt.
            who = "the owner" if m.from_owner else _clean(_line(m.sender).replace('"', ""))
            body = _clean(m.body)
            messages.append(
                f'<message from="{who}" date="{_day(m.received_at)}">\n{body}\n</message>'
            )
        sections.append("Earlier messages in this thread, oldest first:\n" + "\n".join(messages))
    if history.corrections and history.corrections.items:
        lines = ["Owner corrections in this business, newest first:"]
        for c in history.corrections.items:
            was = _clean(_line(c.from_value)) if c.from_value is not None else "nothing"
            # Drop quotes before cleaning (as for from=): the text sits inside our own quotes.
            subject = _clean(_line(c.subject).replace('"', ""))
            lines.append(
                f'- "{subject}": Herald said {was}; '
                f"the owner changed it to {_clean(_line(c.to_value))}."
            )
        sections.append("\n".join(lines))
    if not sections:
        return ""
    return "<history>\n" + "\n\n".join(sections) + "\n</history>"


def user_message(email: Email, important: bool, history: History) -> str:
    """What Claude reads for one email: the history (when there is any), then the email."""
    block = history_block(history)
    email_text = email_block(email, important)
    return f"{block}\n\n{email_text}" if block else email_text
