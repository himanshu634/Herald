"""The prompt Claude reads for each email.

The fixed instructions come from triage.md; the business block is built from the
workspace's config.
"""

from importlib.resources import files

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
    return f"<email>\nFrom: {sender}\nSubject: {_line(email.subject)}\n\n{email.body}\n</email>"
