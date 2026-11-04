"""Checks on the eval harness itself. No scores are asserted: those come from a real model."""

from contextlib import contextmanager
from pathlib import Path

import pytest
from pydantic import ValidationError

from herald_core.model import FakeModel, ModelError
from herald_core.schema import Decision, Notes, Quote, Route, RuleVerdict, Urgency
from herald_evals import dataset as ds
from herald_evals.cli import main
from herald_evals.report import markdown
from herald_evals.runner import Trial, run_all
from herald_evals.score import check, grounded, rule_talk, score_trials, summarise
from herald_server.seed import TRIPFOLD
from herald_server.tracing import NO_TRACING, Run


@pytest.mark.parametrize("name", ds.builtin_names())
def test_builtin_datasets_load(name):
    data = ds.load_named(name)
    assert data.cases
    # Every case says something that can be scored beyond the route, or is about the route.
    assert all(c.expect.route for c in data.cases)


def test_tripfold_uses_the_seed_config():
    # A copy would drift from the product the first time someone edits a seed rule.
    assert ds.load_named("tripfold").config is TRIPFOLD


def _dataset(tmp_path: Path, expect: str) -> Path:
    path = tmp_path / "shop.toml"
    path.write_text(
        f"""
business = "Shop"
config_ref = "herald_server.seed:TRIPFOLD"

[[cases]]
id = "c1"
sender = "a@b.in"
subject = "Hi"
body = "Where is my order?"
[cases.expect]
{expect}
""",
        encoding="utf-8",
    )
    return path


def test_unknown_rule_in_a_label_is_refused(tmp_path):
    with pytest.raises(ValidationError, match="unknown rules"):
        ds.load(_dataset(tmp_path, 'route = "inbox"\nrules = { nope = true }'))


def test_unknown_topic_in_a_label_is_refused(tmp_path):
    with pytest.raises(ValidationError, match="unknown topics"):
        ds.load(_dataset(tmp_path, 'route = "inbox"\ntopic = "Shoes"'))


def test_one_or_several_routes(tmp_path):
    one = ds.load(_dataset(tmp_path, 'route = "alert"')).cases[0].expect
    several = ds.load(_dataset(tmp_path, 'route = ["inbox", "alert"]')).cases[0].expect
    none = ds.load(_dataset(tmp_path, 'route = "inbox"')).cases[0].expect
    assert (one.should_alert, several.should_alert, none.should_alert) == (True, None, False)


def _case(**expect):
    return ds.Case(
        id="c1",
        sender="a@b.in",
        subject="Flight   tomorrow",
        body="My bag has not arrived.\nI fly tomorrow at 7 am.",
        expect=ds.Expect(**expect),
    )


def _trial(route=Route.INBOX, quotes=(), verdicts=(), word_flags=(), errors=()):
    notes = Notes(
        topic="Orders and delivery",
        urgency=Urgency.HIGH,
        anger=2,
        summary="Bag late before a flight.",
        quotes=[Quote(note="urgency", text=t) for t in quotes],
        sure=True,
    )
    return Trial(
        dataset="d",
        case_id="c1",
        run=0,
        notes=notes,
        verdicts=list(verdicts),
        word_flags=list(word_flags),
        decision=Decision(route=route, urgency=Urgency.HIGH, reason="test"),
        errors=list(errors),
        ms=5,
    )


def test_summaries_that_talk_about_rules_are_caught():
    ids = {"travel-soon", "corporate"}
    assert rule_talk("The travel-soon rule does not match.", ids)
    assert rule_talk("Not travel-soon.", ids)
    assert not rule_talk("A corporate order for 250 bags.", ids)
    assert not rule_talk("Bag late before a flight.", ids)


def test_quotes_are_matched_with_whitespace_collapsed():
    case = _case(route="alert")
    assert grounded("I fly   tomorrow at 7 am.", case)
    assert grounded('"Flight tomorrow"', case)
    # The <email> block's header lines are lines of the email too.
    assert grounded("Subject: Flight tomorrow", case)
    assert not grounded("I fly on Friday", case)
    assert not grounded("  ", case)


def test_checks_cover_each_label():
    case = _case(
        route="alert",
        topic="Orders and delivery",
        anger=[3, 4],
        rules={"travel-soon": True, "damaged": False},
        no_flags=["legal_threat"],
    )
    trial = _trial(
        quotes=["I fly tomorrow at 7 am.", "from the history"],
        verdicts=[RuleVerdict(rule_id="travel-soon", matched=True)],
        word_flags=["legal_threat"],
    )
    results = {c.name: c.ok for c in check(case, trial)}
    assert results == {
        "route": False,
        "topic": True,
        "anger": False,
        "no_flag:legal_threat": False,
        "rule:travel-soon": True,
        # Not judged counts as "no", which is what this label wants.
        "rule:damaged": True,
        "quote": False,
    }


def test_model_errors_are_left_out_of_quality_numbers():
    case = _case(route="alert")
    cases = {("d", "c1"): case}
    ok = score_trials(cases, [_trial(route=Route.ALERT)])
    broken = score_trials(cases, [_trial(route=Route.NEEDS_A_LOOK, errors=["write_notes: 429"])])
    scores = summarise([*ok, *broken])
    assert scores.model_errors == 1
    assert str(scores.missed_alerts) == "0% (0/1)"
    assert str(scores.needs_a_look) == "0% (0/1)"


def test_false_alarms_count_alerts_on_should_not_alert_cases():
    cases = {("d", "c1"): _case(route="inbox")}
    scores = summarise(score_trials(cases, [_trial(route=Route.ALERT)]))
    assert str(scores.false_alarms) == "100% (1/1)"
    assert str(scores.missed_alerts) == "—"


class FailingModel(FakeModel):
    async def write_notes(self, email, business_name, config, history=None, tools=()):
        raise ModelError("rate limited")


async def test_runner_records_model_errors_the_graph_swallows():
    data = ds.load_named("tripfold")
    trials = await run_all(FailingModel(), [(data, data.cases[0])])
    assert trials[0].errors == ["write_notes: rate limited"]
    assert trials[0].decision.route is Route.NEEDS_A_LOOK


async def test_runner_feeds_recorded_history_to_the_model():
    seen = []

    class Spy(FakeModel):
        async def write_notes(self, email, business_name, config, history=None, tools=()):
            seen.append((email.thread_id, history))
            return await super().write_notes(email, business_name, config, history)

    data = ds.load_named("tripfold")
    case = next(c for c in data.cases if c.history and c.history.thread)
    await run_all(Spy(), [(data, case)])
    thread_id, history = seen[0]
    assert thread_id is not None
    assert history.thread and history.thread.messages


def test_fake_run_writes_a_report(tmp_path, capsys):
    main(["--model", "fake", "--out", str(tmp_path)])
    files = sorted(p.suffix for p in tmp_path.iterdir())
    assert files == [".json", ".md"]
    assert "# Herald score report" in capsys.readouterr().out


def test_rescore_reads_an_earlier_run_without_a_model(tmp_path, capsys):
    main(["--model", "fake", "--dataset", "ledgerly", "--out", str(tmp_path / "first")])
    first = next((tmp_path / "first").glob("*.json"))
    capsys.readouterr()
    main(["--rescore", str(first), "--out", str(tmp_path / "again")])
    again = next((tmp_path / "again").glob("*.json"))
    assert again.name.endswith("-rescored.json")
    assert "ledgerly" in capsys.readouterr().out


def test_report_names_unreviewed_cases():
    cases = {("d", "c1"): _case(route="inbox")}
    meta = {
        "model": "fake",
        "model_name": "fake",
        "temperature": "n/a",
        "repeats": 1,
        "prompt_hash": "x",
        "commit": "y",
        "started": "now",
    }
    text = markdown(meta, score_trials(cases, [_trial()]))
    assert "1 of 1 cases are not hand-checked yet" in text


class RecordingTracing:
    """A Tracing that records run() calls and scores. Copied from the server tests."""

    enabled = True

    def __init__(self) -> None:
        self.runs: list[tuple[str, dict]] = []
        self.scores: list[tuple[str | None, str, object]] = []

    def wrap_model(self, model):
        return model

    @contextmanager
    def run(self, name, **kwargs):
        self.runs.append((name, kwargs))
        yield Run("trace-1", [])

    def score(self, trace_id, name, value) -> None:
        self.scores.append((trace_id, name, value))

    def shutdown(self) -> None:
        pass


async def test_run_all_traces_each_trial():
    tracing = RecordingTracing()
    data = ds.load_named("tripfold")
    trials = await run_all(
        FakeModel(), [(data, data.cases[0])], repeats=2, tracing=tracing, session="eval-test"
    )
    assert [r[0] for r in tracing.runs] == ["eval", "eval"]
    kw = tracing.runs[0][1]
    assert kw["session_id"] == "eval-test" and kw["tags"] == ["eval", "tripfold"]
    assert all(t.trace_id == "trace-1" for t in trials)  # the stub's fixed id
    assert {s[1] for s in tracing.scores} == {"route", "floor", "unsure", "ai_failed"}


def test_traces_carry_the_model_the_run_uses(tmp_path, monkeypatch):
    seen = []

    def capture(settings):
        seen.append(settings)
        return NO_TRACING

    monkeypatch.setattr("herald_evals.cli.build_tracing", capture)
    # Settings say Claude; the run uses the fake model, so the tag must say "fake".
    monkeypatch.setenv("HERALD_MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("HERALD_MODEL_NAME", "claude-from-env")
    main(["--model", "fake", "--dataset", "ledgerly", "--out", str(tmp_path)])
    assert seen[0].model_provider == "fake"
    assert seen[0].model_name == "claude-from-env"  # build_tracing turns fake into the tag
