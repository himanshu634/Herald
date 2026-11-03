"""Score trials against their labels.

Each trial gets a list of checks, one per labelled thing. The headline numbers follow the
success measures in docs/product-scope.md: missed alerts first, then false alarms, topic
accuracy, the needs-a-look share and rule accuracy.

A trial with a model error (outage, rate limit, bad output) is left out of every quality
number and counted on its own: it says nothing about how well the AI reads email.
"""

import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel

from herald_core.schema import FLOOR_FLAGS, Route
from herald_evals.dataset import Case
from herald_evals.runner import Trial

# Proposed targets from docs/product-scope.md, "Success measures".
TARGETS = {
    "missed_alerts": ("<=", 0.05),
    "false_alarms": ("<=", 0.30),
    "topic": (">=", 0.85),
    "needs_a_look": ("<", 0.10),
    "rules": (">=", 0.90),
}


class Check(BaseModel):
    name: str
    ok: bool
    expected: str
    got: str


def _norm(text: str) -> str:
    # The model re-wraps lines and the prompt collapses the subject's whitespace, so quotes
    # are compared with all whitespace collapsed and case folded.
    return " ".join(text.split()).casefold()


_QUOTE_MARKS = re.compile(r"^[\"'“”‘’]+|[\"'“”‘’]+$")


def grounded(quote: str, case: Case) -> bool:
    """True when the quote is a line from this email, not from history.

    The prompt asks for lines from the <email> block, whose header lines ("From: ...",
    "Subject: ...") count as lines of the email.
    """
    text = _norm(_QUOTE_MARKS.sub("", quote.strip()))
    email = f"From: {case.sender}\nSubject: {case.subject}\n{case.body}"
    return bool(text) and text in _norm(email)


def rule_talk(summary: str, rule_ids: Iterable[str]) -> bool:
    """True when the summary talks about the owner's rules instead of the email.

    The summary is what the owner reads on an alert. Rule verdicts have their own call, so a
    line like "the travel-soon rule does not match" is noise to them. Only ids with a dash or
    underscore are matched: a plain-word id such as "corporate" is also an ordinary word.
    """
    ids = [re.escape(i) for i in rule_ids if re.search(r"[-_]", i)]
    pattern = "|".join([r"\brules?\b", *(rf"\b{i}\b" for i in ids)])
    return re.search(pattern, summary, re.I) is not None


def check(case: Case, trial: Trial, rule_ids: Iterable[str] = ()) -> list[Check]:
    expect, notes = case.expect, trial.notes
    checks = [
        Check(
            name="route",
            ok=trial.decision.route in expect.route,
            expected=" or ".join(expect.route),
            got=f"{trial.decision.route} ({trial.decision.reason})",
        )
    ]
    no_notes = "no notes"
    if expect.topic:
        got = notes.topic if notes else no_notes
        ok = notes is not None and _norm(got) in {_norm(t) for t in expect.topic}
        checks.append(Check(name="topic", ok=ok, expected=" or ".join(expect.topic), got=got))
    if expect.urgency:
        got = notes.urgency if notes else no_notes
        ok = notes is not None and notes.urgency in expect.urgency
        checks.append(
            Check(name="urgency", ok=ok, expected=" or ".join(expect.urgency), got=str(got))
        )
    if expect.anger:
        lo, hi = expect.anger
        got = notes.anger if notes else None
        checks.append(
            Check(
                name="anger",
                ok=got is not None and lo <= got <= hi,
                expected=f"{lo}" if lo == hi else f"{lo}-{hi}",
                got=str(got) if got is not None else no_notes,
            )
        )
    ai_flags = set(notes.risk_flags) if notes else set()
    for flag in expect.flags:
        checks.append(
            Check(
                name=f"flag:{flag}",
                ok=flag in ai_flags,
                expected="AI adds it",
                got=", ".join(sorted(ai_flags)) or "no flags",
            )
        )
    raised = ai_flags | set(trial.word_flags)
    for flag in expect.no_flags:
        source = [s for s, fs in (("AI", ai_flags), ("word check", trial.word_flags)) if flag in fs]
        checks.append(
            Check(
                name=f"no_flag:{flag}",
                ok=flag not in raised,
                expected="not raised",
                got="raised by " + " and ".join(source) if source else "not raised",
            )
        )
    verdicts = {v.rule_id: v for v in trial.verdicts}
    for rule_id, want in expect.rules.items():
        verdict = verdicts.get(rule_id)
        # No verdict (rules skipped for not-for-business mail, or a missing answer) is a "no".
        matched = verdict.matched if verdict else False
        got = ("yes" if matched else "no") + (
            f' "{verdict.quote}"' if verdict and verdict.quote else ""
        )
        checks.append(
            Check(
                name=f"rule:{rule_id}",
                ok=matched == want,
                expected="yes" if want else "no",
                got=got if verdict else "no (not judged)",
            )
        )
    if notes and rule_talk(notes.summary, rule_ids):
        checks.append(
            Check(
                name="summary",
                ok=False,
                expected="about the email, not the rules",
                got=notes.summary,
            )
        )
    for quote in notes.quotes if notes else []:
        if not grounded(quote.text, case):
            checks.append(
                Check(
                    name="quote",
                    ok=False,
                    expected="a line from the email",
                    got=f'{quote.note}: "{quote.text}"',
                )
            )
    return checks


@dataclass
class Ratio:
    hit: int = 0
    total: int = 0

    def add(self, ok: bool) -> None:
        self.hit += ok
        self.total += 1

    @property
    def value(self) -> float | None:
        return self.hit / self.total if self.total else None

    def __str__(self) -> str:
        if not self.total:
            return "—"
        return f"{self.value:.0%} ({self.hit}/{self.total})"


@dataclass
class Scored:
    case: Case
    trial: Trial
    checks: list[Check]

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]


@dataclass
class RuleScore:
    right: Ratio = field(default_factory=Ratio)
    false_yes: int = 0
    false_no: int = 0


@dataclass
class Scores:
    trials: int = 0
    model_errors: int = 0
    cases: int = 0
    reviewed_cases: int = 0
    passed: Ratio = field(default_factory=Ratio)
    route: Ratio = field(default_factory=Ratio)
    # Of the trials that should alert, how many did not (lower is better).
    missed_alerts: Ratio = field(default_factory=Ratio)
    # Of the alerts raised on clearly labelled trials, how many should not have been.
    false_alarms: Ratio = field(default_factory=Ratio)
    topic: Ratio = field(default_factory=Ratio)
    urgency: Ratio = field(default_factory=Ratio)
    anger: Ratio = field(default_factory=Ratio)
    needs_a_look: Ratio = field(default_factory=Ratio)
    rules: Ratio = field(default_factory=Ratio)
    per_rule: dict[str, RuleScore] = field(default_factory=lambda: defaultdict(RuleScore))
    # Safety floor flags the label expects, caught by the AI, the word check, or either.
    floor_ai: Ratio = field(default_factory=Ratio)
    floor_words: Ratio = field(default_factory=Ratio)
    floor_either: Ratio = field(default_factory=Ratio)
    # Trials where the word check raised a floor flag the label does not expect. The floor
    # always alerts, so each one is an alert no rule can undo.
    word_false_alarms: Counter = field(default_factory=Counter)
    quotes: Ratio = field(default_factory=Ratio)
    # Summaries that stay about the email (see `rule_talk`).
    summaries: Ratio = field(default_factory=Ratio)
    by_tag: dict[str, Ratio] = field(default_factory=lambda: defaultdict(Ratio))
    confusion: Counter = field(default_factory=Counter)
    ms: list[int] = field(default_factory=list)

    @property
    def latency(self) -> tuple[int, int] | None:
        if not self.ms:
            return None
        ordered = sorted(self.ms)
        p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
        return round(statistics.median(ordered)), p95


def score_trials(
    cases: dict[tuple[str, str], Case],
    trials: Iterable[Trial],
    rule_ids: dict[str, set[str]] | None = None,
) -> list[Scored]:
    """`rule_ids` maps each dataset to its config's rule ids, for the summary check."""
    rule_ids = rule_ids or {}
    return [
        Scored(
            case=(case := cases[(t.dataset, t.case_id)]),
            trial=t,
            checks=check(case, t, rule_ids.get(t.dataset, set())),
        )
        for t in trials
    ]


def summarise(scored: Sequence[Scored]) -> Scores:
    s = Scores()
    case_keys = {(x.trial.dataset, x.case.id) for x in scored}
    s.cases = len(case_keys)
    s.reviewed_cases = len({(x.trial.dataset, x.case.id) for x in scored if x.case.reviewed})
    for x in scored:
        s.trials += 1
        if x.trial.errors:
            s.model_errors += 1
            continue
        expect, trial, notes = x.case.expect, x.trial, x.trial.notes
        got = trial.decision.route
        s.passed.add(x.passed)
        s.ms.append(trial.ms)
        for c in x.checks:
            if c.name == "route":
                s.route.add(c.ok)
            elif c.name in ("topic", "urgency", "anger"):
                getattr(s, c.name).add(c.ok)
            elif c.name.startswith("rule:"):
                s.rules.add(c.ok)
                rule = s.per_rule[c.name.removeprefix("rule:")]
                rule.right.add(c.ok)
                if not c.ok:
                    if c.expected == "yes":
                        rule.false_no += 1
                    else:
                        rule.false_yes += 1
        s.needs_a_look.add(got is Route.NEEDS_A_LOOK)
        if expect.should_alert is True:
            s.missed_alerts.add(got is not Route.ALERT)
        if expect.should_alert is not None and got is Route.ALERT:
            s.false_alarms.add(expect.should_alert is False)
        ai_flags = set(notes.risk_flags) if notes else set()
        for flag in expect.floor:
            s.floor_ai.add(flag in ai_flags)
            s.floor_words.add(flag in trial.word_flags)
            s.floor_either.add(flag in ai_flags or flag in trial.word_flags)
        if extra := (set(trial.word_flags) & FLOOR_FLAGS) - expect.floor:
            s.word_false_alarms[f"{trial.dataset}/{x.case.id}: {', '.join(sorted(extra))}"] += 1
        for quote in notes.quotes if notes else []:
            s.quotes.add(grounded(quote.text, x.case))
        if notes:
            s.summaries.add(all(c.name != "summary" for c in x.checks))
        for tag in x.case.tags:
            s.by_tag[tag].add(x.passed)
        label = expect.route[0] if len(expect.route) == 1 else "either"
        s.confusion[(label, got.value)] += 1
    return s


def meets(metric: str, ratio: Ratio) -> bool | None:
    if metric not in TARGETS or ratio.value is None:
        return None
    op, target = TARGETS[metric]
    v = ratio.value
    return v <= target if op == "<=" else v >= target if op == ">=" else v < target


def flaky(scored: Sequence[Scored]) -> dict[tuple[str, str], Counter]:
    """Cases whose route changed between runs of the same model and prompt."""
    routes: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for x in scored:
        if not x.trial.errors:
            routes[(x.trial.dataset, x.case.id)][x.trial.decision.route.value] += 1
    return {k: v for k, v in routes.items() if len(v) > 1}
