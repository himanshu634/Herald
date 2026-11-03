"""The score report (Markdown) and the run record (JSON) it is built from.

The JSON keeps every trial with its notes, verdicts and decision, so a later run can be
compared case by case (`--compare`), and a failure can be read without running it again.
"""

import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from herald_evals.score import TARGETS, Ratio, Scored, Scores, flaky, meets, summarise

ROUTES = ["alert", "needs_a_look", "inbox", "closed"]


def run_record(meta: dict, datasets: dict, scored: Sequence[Scored]) -> dict:
    return {
        "meta": meta,
        "datasets": datasets,
        "trials": [
            x.trial.model_dump(mode="json")
            | {"passed": x.passed, "failed": [c.model_dump() for c in x.failed]}
            for x in scored
        ],
    }


def _mark(metric: str, ratio: Ratio) -> str:
    ok = meets(metric, ratio)
    return "" if ok is None else " ✓" if ok else " ✗"


def _target(metric: str) -> str:
    if metric not in TARGETS:
        return ""
    op, value = TARGETS[metric]
    return f"{op.replace('<=', '≤').replace('>=', '≥')} {value:.0%}"


def _headline(columns: dict[str, Scores]) -> list[str]:
    names = list(columns)
    lines = [
        "| Measure | " + " | ".join(names) + " | Target |",
        "| --- | " + " | ".join("---" for _ in names) + " | --- |",
    ]
    rows = [
        ("Missed alerts", "missed_alerts"),
        ("False alarms", "false_alarms"),
        ("Topic accuracy", "topic"),
        ("Needs a look", "needs_a_look"),
        ("Rule verdicts right", "rules"),
        ("Route right", "route"),
        ("Every label right", "passed"),
        ("Urgency right", "urgency"),
        ("Anger in range", "anger"),
        ("Quotes taken from the email", "quotes"),
    ]
    for label, metric in rows:
        cells = [
            f"{getattr(s, metric)}{_mark(metric, getattr(s, metric))}" for s in columns.values()
        ]
        lines.append(f"| {label} | " + " | ".join(cells) + f" | {_target(metric)} |")
    errors = [f"{s.model_errors} of {s.trials}" for s in columns.values()]
    lines.append("| Model errors (left out above) | " + " | ".join(errors) + " | 0 |")
    latency = [f"{lat[0]} / {lat[1]} ms" if (lat := s.latency) else "—" for s in columns.values()]
    lines.append("| Time per email, median / p95 | " + " | ".join(latency) + " | |")
    return lines


def _cell(text: str) -> str:
    # Model text can hold a pipe or a newline, either of which would break the table row.
    return " ".join(text.split()).replace("|", "\\|")


def _case_detail(runs: list[Scored]) -> list[str]:
    first = next(x for x in runs if not x.passed)
    case, trial, notes = first.case, first.trial, first.trial.notes
    failed_runs = sum(not x.passed for x in runs)
    tags = f" · {', '.join(case.tags)}" if case.tags else ""
    lines = [
        f"### {trial.dataset}/{case.id}{tags}",
        "",
        f"Failed {failed_runs} of {len(runs)} runs. Subject: {case.subject!r}. "
        + ("Hand-checked." if case.reviewed else "Not hand-checked yet."),
    ]
    if case.note:
        lines += ["", f"Label note: {case.note}"]
    lines += ["", "| Check | Expected | Got |", "| --- | --- | --- |"]
    lines += [f"| {c.name} | {_cell(c.expected)} | {_cell(c.got)} |" for c in first.failed]
    if notes:
        flags = ", ".join(notes.risk_flags) or "none"
        words = ", ".join(trial.word_flags) or "none"
        lines += [
            "",
            f"Notes: topic {notes.topic!r}, urgency {notes.urgency}, anger {notes.anger}, "
            f"flags {flags}, sure {notes.sure}. Word check: {words}.",
            f"Summary: {notes.summary}",
        ]
        for q in notes.quotes:
            lines.append(f'- {q.note}: "{q.text}"')
    if trial.verdicts:
        said = "; ".join(
            f"{v.rule_id} {'yes' if v.matched else 'no'}" + (f' "{v.quote}"' if v.quote else "")
            for v in trial.verdicts
        )
        lines += ["", f"Rule verdicts: {said}"]
    return lines + [""]


def compare(previous: dict, scored: Sequence[Scored]) -> list[str]:
    def by_case(trials) -> dict[tuple[str, str], tuple[int, int]]:
        out: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
        for t in trials:
            if t["errors"]:
                continue
            key = (t["dataset"], t["case_id"])
            out[key][0] += t["passed"]
            out[key][1] += 1
        return {k: (v[0], v[1]) for k, v in out.items()}

    before = by_case(previous["trials"])
    now = by_case([x.trial.model_dump(mode="json") | {"passed": x.passed} for x in scored])
    fixed, broke = [], []
    for key in sorted(before.keys() & now.keys()):
        (bp, bt), (np_, nt) = before[key], now[key]
        name = f"{key[0]}/{key[1]} ({bp}/{bt} → {np_}/{nt} runs right)"
        if np_ / nt > bp / bt:
            fixed.append(name)
        elif np_ / nt < bp / bt:
            broke.append(name)
    meta = previous.get("meta", {})
    lines = [
        "## Changes since the compared run",
        "",
        f"Compared with {meta.get('started', '?')}, model {meta.get('model_name', '?')}, "
        f"prompt {meta.get('prompt_hash', '?')}.",
        "",
        f"Now right more often ({len(fixed)}):",
        *(f"- {n}" for n in fixed or ["none"]),
        "",
        f"Now wrong more often ({len(broke)}):",
        *(f"- {n}" for n in broke or ["none"]),
        "",
    ]
    return lines


def markdown(meta: dict, scored: Sequence[Scored], previous: dict | None = None) -> str:
    datasets = sorted({x.trial.dataset for x in scored})
    columns = {d: summarise([x for x in scored if x.trial.dataset == d]) for d in datasets}
    total = summarise(scored)
    if len(datasets) > 1:
        columns["All"] = total

    lines = [
        "# Herald score report",
        "",
        f"Model `{meta['model_name']}` ({meta['model']}), temperature {meta['temperature']}, "
        f"{meta['repeats']} run(s) per case, prompt `{meta['prompt_hash']}`, "
        f"commit `{meta['commit']}`, {meta['started']}.",
        "",
    ]
    if total.reviewed_cases < total.cases:
        lines += [
            f"> **{total.cases - total.reviewed_cases} of {total.cases} cases are not hand-checked "
            "yet.** They were drafted with an AI's help. Read each one and set `reviewed = true` "
            "when you agree with its label; until then these numbers are a draft.",
            "",
        ]
    lines += ["## Headline", "", *_headline(columns), ""]
    reviewed = [x for x in scored if x.case.reviewed]
    if reviewed and total.reviewed_cases < total.cases:
        lines += [
            "### Hand-checked cases only",
            "",
            *_headline({"Hand-checked": summarise(reviewed)}),
            "",
        ]

    lines += [
        "## Safety floor",
        "",
        "Floor flags the labels expect, and who caught them. The word check runs beside the AI; "
        "either one alerts.",
        "",
        "| Caught by | Share |",
        "| --- | --- |",
        f"| AI | {total.floor_ai} |",
        f"| Word check | {total.floor_words} |",
        f"| Either (what the owner gets) | {total.floor_either} |",
        "",
        "Word check raised a floor flag the label does not expect "
        f"({len(total.word_false_alarms)}). No rule can undo these alerts:",
        *(f"- {w}" for w in sorted(set(total.word_false_alarms)) or ["none"]),
        "",
        "## Rules",
        "",
        "| Rule | Right | Said yes, should be no | Said no, should be yes |",
        "| --- | --- | --- | --- |",
    ]
    for d, s in columns.items():
        if d == "All":
            continue
        for rule_id, r in sorted(s.per_rule.items()):
            lines.append(f"| {d}/{rule_id} | {r.right} | {r.false_yes} | {r.false_no} |")
    lines += ["", "## Slices", "", "| Tag | Every label right |", "| --- | --- |"]
    lines += [f"| {tag} | {r} |" for tag, r in sorted(total.by_tag.items())]

    lines += [
        "",
        "## Routes",
        "",
        "Rows are the label, columns what Herald did. `either` is a case where more than one "
        "route is fine.",
        "",
        "| Label \\ Got | " + " | ".join(ROUTES) + " |",
        "| --- | " + " | ".join("---" for _ in ROUTES) + " |",
    ]
    for label in [*ROUTES, "either"]:
        counts = [total.confusion.get((label, got), 0) for got in ROUTES]
        if any(counts):
            lines.append(f"| {label} | " + " | ".join(str(c) for c in counts) + " |")

    unstable = flaky(scored)
    if meta["repeats"] > 1:
        lines += ["", f"## Cases whose route changed between runs ({len(unstable)})", ""]
        for (d, case_id), routes in sorted(unstable.items()):
            lines.append(f"- {d}/{case_id}: " + ", ".join(f"{r} ×{n}" for r, n in routes.items()))

    runs: dict[tuple[str, str], list[Scored]] = defaultdict(list)
    for x in scored:
        if not x.trial.errors:
            runs[(x.trial.dataset, x.case.id)].append(x)
    failing = [r for r in runs.values() if any(not x.passed for x in r)]
    lines += ["", f"## Failing cases ({len(failing)})", ""]
    for case_runs in sorted(failing, key=lambda r: (r[0].trial.dataset, r[0].case.id)):
        lines += _case_detail(case_runs)

    errored = [x for x in scored if x.trial.errors]
    if errored:
        lines += [f"## Model errors ({len(errored)})", ""]
        lines += [f"- {x.trial.dataset}/{x.case.id}: {'; '.join(x.trial.errors)}" for x in errored]
        lines.append("")

    if previous:
        lines += compare(previous, scored)
    return "\n".join(lines).rstrip() + "\n"


def write(out_dir: Path, stem: str, record: dict, report: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out_dir / f"{stem}.json", out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(report, encoding="utf-8")
    return json_path, md_path
