import pytest
from pydantic import ValidationError

from herald_core.model import FakeModel
from herald_core.schema import Rule, RuleAction, WorkspaceConfig


def config(**changes) -> WorkspaceConfig:
    data = {"business_profile": "We bake custom cakes.", "topics": ["Orders"]} | changes
    return WorkspaceConfig.model_validate(data)


def test_config_needs_a_topic():
    with pytest.raises(ValidationError):
        config(topics=[])
    with pytest.raises(ValidationError):
        config(topics=["  "])


def test_set_urgency_rule_needs_an_urgency():
    with pytest.raises(ValidationError):
        Rule(id="r", name="R", when="It is about cake", action=RuleAction.SET_URGENCY)


def test_rule_ids_are_unique():
    rule = {"id": "r", "name": "R", "when": "It is about cake", "action": "alert"}
    with pytest.raises(ValidationError):
        config(rules=[rule, rule])


def test_old_configs_without_guidance_still_load():
    assert config().guidance == []


async def test_fake_suggest_setup_is_deterministic():
    model = FakeModel()
    description = "We take cake orders and deliver on the day. Refunds by bank transfer."
    first = await model.suggest_setup("Crumb", description)
    assert first == await model.suggest_setup("Crumb", description)
    assert [t.name for t in first.topics] == [
        "Orders and delivery",
        "Payments and refunds",
        "Questions",
    ]
    assert all(t.meaning for t in first.topics)
    assert first.facts == []
    assert first.rules


def test_string_topics_still_load():
    loaded = config(topics=["Orders", "Refunds"])
    assert [t.name for t in loaded.topics] == ["Orders", "Refunds"]
    assert all(t.meaning is None for t in loaded.topics)


def test_topics_can_carry_a_meaning():
    loaded = config(topics=[{"name": "Orders", "meaning": "Where an order is"}])
    assert loaded.topics[0].meaning == "Where an order is"


def test_blank_meaning_becomes_none():
    assert config(topics=[{"name": "Orders", "meaning": "   "}]).topics[0].meaning is None


def test_topic_names_are_unique_ignoring_case():
    with pytest.raises(ValidationError):
        config(topics=["Orders", "orders"])


def test_facts_are_capped():
    assert config().facts == []
    with pytest.raises(ValidationError):
        config(facts=[f"Fact {i}" for i in range(11)])
    with pytest.raises(ValidationError):
        config(facts=["x" * 201])
    with pytest.raises(ValidationError):
        config(topics=[{"name": "Orders", "meaning": "x" * 121}])
