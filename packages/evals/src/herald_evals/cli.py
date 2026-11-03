"""`herald-evals`: run the test emails through triage and write the score report.

uv run herald-evals                         # every dataset, Claude, one run each
uv run herald-evals --repeats 3             # three runs each, to see unstable cases
uv run herald-evals --case sue-is-a-name    # one case while fixing it
uv run herald-evals --compare packages/evals/results/<earlier>.json
uv run herald-evals --rescore packages/evals/results/<earlier>.json   # new labels, no calls
uv run herald-evals --model fake            # offline smoke run of the harness itself
"""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from anthropic import AsyncAnthropic

from herald_core.model import DEFAULT_MODEL, AnthropicModel, FakeModel, TriageModel
from herald_core.prompt import TRIAGE_INSTRUCTIONS
from herald_evals import dataset as ds
from herald_evals.report import markdown, run_record, write
from herald_evals.runner import Trial, run_all, stderr
from herald_evals.score import Scored, score_trials
from herald_server.settings import get_settings
from herald_server.tracing import build_tracing

RESULTS = Path(__file__).resolve().parents[2] / "results"


def _load_dotenv() -> None:
    """Read ANTHROPIC_API_KEY from the nearest .env when it is not set.

    The server's settings read only HERALD_* names, and the Anthropic client reads the
    process environment, so a key kept in .env would otherwise never reach it.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    for folder in [Path.cwd(), *Path.cwd().parents]:
        env = folder / ".env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip() == "ANTHROPIC_API_KEY" and value.strip():
                    os.environ["ANTHROPIC_API_KEY"] = value.strip().strip("\"'")
            return


def _model(provider: str, name: str) -> TriageModel:
    if provider == "fake":
        return FakeModel()
    _load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set (in the environment or .env).")
    # More retries than the default 2: a burst of parallel calls can hit the rate limit, and
    # a call that still fails is reported as a model error, not a wrong answer.
    return AnthropicModel(AsyncAnthropic(max_retries=6), model=name)


def _commit() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{sha}+changes" if dirty else sha


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="herald-evals", description=__doc__.split("\n")[0])
    parser.add_argument(
        "--dataset",
        action="append",
        help=f"Built-in name or a TOML path. Default: all ({', '.join(ds.builtin_names())}).",
    )
    parser.add_argument("--model", choices=["anthropic", "fake"], default="anthropic")
    parser.add_argument("--model-name", default=os.environ.get("HERALD_MODEL_NAME", DEFAULT_MODEL))
    parser.add_argument("--repeats", type=int, default=1, help="Runs per case.")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--case", action="append", help="Run only these case ids.")
    parser.add_argument("--tag", action="append", help="Run only cases with one of these tags.")
    parser.add_argument("--reviewed-only", action="store_true", help="Only hand-checked cases.")
    parser.add_argument("--compare", type=Path, help="An earlier run's JSON to compare with.")
    parser.add_argument("--out", type=Path, default=RESULTS, help="Where results are written.")
    parser.add_argument(
        "--rescore",
        type=Path,
        help="Score an earlier run's JSON against the current labels, with no model calls.",
    )
    args = parser.parse_args(argv)

    recorded = json.loads(args.rescore.read_text(encoding="utf-8")) if args.rescore else None
    names = args.dataset or (list(recorded["datasets"]) if recorded else ds.builtin_names())
    datasets = [ds.load_named(n) for n in names]
    work = [
        (d, c)
        for d in datasets
        for c in d.cases
        if (not args.case or c.id in args.case)
        and (not args.tag or set(c.tags) & set(args.tag))
        and (not args.reviewed_only or c.reviewed)
    ]
    if not work:
        raise SystemExit("No cases match.")
    started = datetime.now(UTC)
    if recorded:
        wanted = {(d.name, c.id) for d, c in work}
        trials = [
            t
            for t in (Trial.model_validate(raw) for raw in recorded["trials"])
            if (t.dataset, t.case_id) in wanted
        ]
        _report(args, datasets, work, trials, recorded["meta"] | {"rescored": _stamp(started)})
        return
    model = _model(args.model, args.model_name)
    # Tracing is on only when the Langfuse keys are set (dev). It is never built for --rescore.
    # Tag traces with the model this run uses, not the one in settings or .env.
    tracing = build_tracing(
        get_settings().model_copy(
            update={"model_provider": args.model, "model_name": args.model_name}
        )
    )
    session = f"eval-{started.strftime('%Y%m%d-%H%M%S')}"
    try:
        trials = asyncio.run(
            run_all(
                model,
                work,
                repeats=args.repeats,
                concurrency=args.concurrency,
                progress=stderr,
                tracing=tracing,
                session=session,
            )
        )
        meta = _meta(args, started)
        if tracing.enabled:
            meta["langfuse_session"] = session
        scored = _report(args, datasets, work, trials, meta)
        for s in scored:
            tracing.score(s.trial.trace_id, "passed", s.passed)
    finally:
        tracing.shutdown()


def _meta(args: argparse.Namespace, started: datetime) -> dict:
    return {
        "started": _stamp(started),
        "model": args.model,
        "model_name": args.model_name if args.model == "anthropic" else "fake",
        # AnthropicModel sets no temperature, so the API default applies.
        "temperature": "API default (1.0)" if args.model == "anthropic" else "n/a",
        "repeats": args.repeats,
        "prompt_hash": hashlib.sha256(TRIAGE_INSTRUCTIONS.encode()).hexdigest()[:12],
        "commit": _commit(),
    }


def _stamp(when: datetime) -> str:
    return when.strftime("%Y-%m-%d %H:%M UTC")


def _report(
    args: argparse.Namespace,
    datasets: list[ds.Dataset],
    work: list[tuple[ds.Dataset, ds.Case]],
    trials: list[Trial],
    meta: dict,
) -> list[Scored]:
    cases = {(d.name, c.id): c for d, c in work}
    rule_ids = {d.name: {r.id for r in d.config.rules} for d in datasets}
    scored = score_trials(cases, trials, rule_ids)
    info = {
        d.name: {"business": d.business, "config_ref": d.config_ref, "config_hash": d.config_hash()}
        for d in datasets
    }
    previous = json.loads(args.compare.read_text(encoding="utf-8")) if args.compare else None
    report = markdown(meta, scored, previous)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    suffix = "-rescored" if "rescored" in meta else ""
    stem = f"{stamp}-{meta['model_name']}{suffix}"
    json_path, md_path = write(args.out, stem, run_record(meta, info, scored), report)
    print(report)
    stderr(f"Report: {md_path}\nRun record: {json_path}")
    return scored


if __name__ == "__main__":
    main()
