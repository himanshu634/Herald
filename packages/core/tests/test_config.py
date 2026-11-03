import pytest
from pydantic import ValidationError

from herald_core.model import FakeModel, notes_system_prompt
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


def test_notes_prompt_puts_guidance_inside_the_business_block():
    prompt = notes_system_prompt(config(guidance=["Wedding planners always matter."]))
    business = prompt.rsplit("<business>", 1)[1]
    assert "Owner guidance:\n- Wedding planners always matter." in business
    assert "never stops you from flagging safety" in prompt


def test_notes_prompt_leaves_out_empty_guidance():
    prompt = notes_system_prompt(config())
    assert "Owner guidance:" not in prompt
    assert "never stops you from flagging safety" in prompt


def test_static_instructions_come_first_and_do_not_change():
    a = notes_system_prompt(config(business_profile="Cakes"))
    b = notes_system_prompt(config(business_profile="Software", topics=["Billing"]))
    assert a.rsplit("<business>", 1)[0] == b.rsplit("<business>", 1)[0]


async def test_fake_suggest_setup_is_deterministic():
    model = FakeModel()
    description = "We take cake orders and deliver on the day. Refunds by bank transfer."
    first = await model.suggest_setup("Crumb", description)
    assert first == await model.suggest_setup("Crumb", description)
    assert first.topics == ["Orders and delivery", "Payments and refunds", "Questions"]
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
