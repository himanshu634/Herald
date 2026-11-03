"""Onboarding: turn a business name and description into a first config the owner edits.

The AI drafts topics with meanings, facts, guidance and rules. Its draft is never trusted as
is: `clean_draft` makes it a valid `WorkspaceConfig`, and if the AI fails the owner gets a plain
fallback instead of an error, so setup never depends on the model being up.
"""

import logging
import re

from herald_core.model import ModelError, TriageModel
from herald_core.schema import (
    SPAM_TOPIC,
    Rule,
    RuleAction,
    SetupDraft,
    Topic,
    WorkspaceConfig,
)

log = logging.getLogger(__name__)

FALLBACK_TOPICS = [Topic(name=n) for n in ("Questions", "Problems", "Billing")]
MAX_TOPICS = 12
MAX_FACTS = 10
MAX_FACT_LENGTH = 200
MAX_MEANING_LENGTH = 120
MAX_GUIDANCE = 8
MAX_RULES = 8


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "rule"


def clean_draft(draft: SetupDraft, description: str) -> WorkspaceConfig:
    topics: list[Topic] = []
    seen = {SPAM_TOPIC.lower()}  # Every email can already go to spam; it is not a topic.
    for draft_topic in draft.topics:
        name = draft_topic.name.strip()[:60]
        if name and name.lower() not in seen:
            seen.add(name.lower())
            meaning = draft_topic.meaning.strip()[:MAX_MEANING_LENGTH].strip() or None
            topics.append(Topic(name=name, meaning=meaning))

    # Facts come from the AI and are judged against real emails, so they are trimmed and
    # capped like every other draft field.
    facts = [f.strip()[:MAX_FACT_LENGTH].strip() for f in draft.facts if f.strip()][:MAX_FACTS]

    guidance = [g.strip()[:300] for g in draft.guidance if g.strip()][:MAX_GUIDANCE]

    rules: list[Rule] = []
    ids: set[str] = set()
    for r in draft.rules:
        if r.action is RuleAction.SET_URGENCY and r.urgency is None:
            continue
        if not r.name.strip() or not r.when.strip():
            continue
        # The model is not trusted to keep ids unique, and verdicts are matched by id.
        base = _slug(r.name)
        rule_id, n = base, 2
        while rule_id in ids:
            rule_id, n = f"{base}-{n}", n + 1
        ids.add(rule_id)
        urgency = r.urgency if r.action is RuleAction.SET_URGENCY else None
        rules.append(
            Rule(
                id=rule_id,
                name=r.name.strip(),
                when=r.when.strip(),
                action=r.action,
                urgency=urgency,
            )
        )
        if len(rules) == MAX_RULES:
            break

    return WorkspaceConfig(
        business_profile=description,
        topics=topics[:MAX_TOPICS] or FALLBACK_TOPICS,
        facts=facts,
        guidance=guidance,
        rules=rules,
    )


def fallback_config(description: str) -> WorkspaceConfig:
    return WorkspaceConfig(business_profile=description, topics=FALLBACK_TOPICS)


async def draft_config(
    model: TriageModel, name: str, description: str
) -> tuple[WorkspaceConfig, bool]:
    """The cleaned AI draft and True, or the fallback and False when the AI fails."""
    try:
        draft = await model.suggest_setup(name, description)
    except ModelError:
        log.warning("Setup draft failed; using the fallback config", exc_info=True)
        return fallback_config(description), False
    return clean_draft(draft, description), True
