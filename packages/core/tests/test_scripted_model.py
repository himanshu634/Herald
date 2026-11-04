import pytest

from herald_core.schema import Email, RuleVerdict, Topic, WorkspaceConfig
from scripted_model import ScriptedModel, plain_notes

CONFIG = WorkspaceConfig(business_profile="Luggage.", topics=[Topic(name="Orders")])
EMAIL = Email(id="e1", workspace_id="w", sender="a@b.c", subject="Where is it?", body="Hi")


async def test_default_notes_use_the_first_topic():
    notes = await ScriptedModel().write_notes(EMAIL, "Tripfold", CONFIG)
    assert notes.topic == "Orders"
    assert notes.sure


async def test_an_exception_is_raised():
    model = ScriptedModel(notes=RuntimeError("down"))
    with pytest.raises(RuntimeError, match="down"):
        await model.write_notes(EMAIL, "Tripfold", CONFIG)


async def test_a_callable_gets_the_email():
    model = ScriptedModel(
        verdicts=lambda email, config: [RuleVerdict(rule_id=email.id, matched=True)]
    )
    assert (await model.judge_rules(EMAIL, "Tripfold", CONFIG))[0].rule_id == "e1"


async def test_calls_are_recorded_in_order():
    model = ScriptedModel(notes=plain_notes(EMAIL, CONFIG, anger=4))
    await model.write_notes(EMAIL, "Tripfold", CONFIG)
    await model.judge_rules(EMAIL, "Tripfold", CONFIG)
    await model.suggest_setup("Tripfold", "Luggage")
    assert [name for name, _ in model.calls] == ["write_notes", "judge_rules", "suggest_setup"]
