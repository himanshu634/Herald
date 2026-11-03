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
