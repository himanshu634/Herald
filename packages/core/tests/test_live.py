"""Smoke tests against the real model. They check the plumbing and that the schemas are
accepted, not the quality of the judgement (the evals measure that)."""

import os
from datetime import datetime

import pytest

from herald_core.history import SenderHistory
from herald_core.providers import load_provider
from herald_core.schema import Email, Rule, RuleAction, WorkspaceConfig
from herald_core.tools import SenderLookup

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY unset"),
]

CONFIG = WorkspaceConfig(
    business_profile="Tripfold sells carry-on luggage online.",
    topics=["Orders and delivery", "Returns"],
    rules=[
        Rule(
            id="r-gift",
            name="Gift orders",
            when="The customer says the order is a gift",
            action=RuleAction.ALERT,
        )
    ],
)


def email(subject: str, body: str) -> Email:
    return Email(id="e1", workspace_id="w1", sender="a@customer.in", subject=subject, body=body)


def model():
    provider = load_provider("openrouter")
    return provider.build(provider.default_model, os.environ["OPENROUTER_API_KEY"])


async def test_live_notes():
    notes = await model().write_notes(
        email("Order #123", "Where is my order #123?"), "Tripfold", CONFIG
    )
    assert notes.topic in {t.name for t in CONFIG.topics}


async def test_live_rules():
    body = "Order #55 is a birthday gift for my sister, it has to arrive by Friday."
    verdicts = await model().judge_rules(email("Gift", body), "Tripfold", CONFIG)
    assert any(v.rule_id == "r-gift" and v.matched for v in verdicts)


async def test_live_setup_draft():
    draft = await model().suggest_setup("Tripfold", "We sell carry-on luggage online.")
    assert len(draft.topics) >= 1


async def test_live_tool_round():
    lookup = SenderLookup(
        SenderHistory(
            first_seen=datetime(2026, 9, 12), count_7d=1, count_30d=1, top_topics=[], recent=[]
        )
    )
    notes = await model().write_notes(
        email("Again", "This is the third time I am asking about my order."),
        "Tripfold",
        CONFIG,
        tools=[lookup],
    )
    assert notes.topic
