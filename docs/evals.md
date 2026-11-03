# Herald: Evals

The evals run test emails with known answers through the real triage graph (word check, history, notes, rule verdicts, decide) and write a score report. They are how we find and fix what Herald gets wrong. They are not a pass/fail gate in CI: the model is not deterministic, and a score is only as good as its labels.

## Run them

```bash
make eval                                   # every dataset on Claude, one run per case
make eval ARGS="--repeats 3"                # three runs each; the report lists cases whose route changed
make eval ARGS="--case sue-is-a-name"       # one case while you fix it
make eval ARGS="--tag safety_floor"         # one slice
make eval ARGS="--compare packages/evals/results/<earlier>.json"
make eval ARGS="--rescore packages/evals/results/<earlier>.json"   # new labels or checks, no model calls
uv run herald-evals --model fake            # offline smoke run of the harness itself
```

`make eval` needs `ANTHROPIC_API_KEY` in the environment or in `.env`. The model is `HERALD_MODEL_NAME` (default `claude-haiku-5-5`), or `--model-name`. Each run writes `<time>-<model>.md` and `.json` to `packages/evals/results/`, which git ignores.

## What is measured

The headline follows "Success measures" in [product-scope.md](product-scope.md).

| Measure | In plain words | Target |
| --- | --- | --- |
| Missed alerts | Of the emails labelled "alert", how many did not alert | ≤ 5% |
| False alarms | Of the alerts on clearly labelled emails, how many should not have alerted | ≤ 30% |
| Topic accuracy | Notes filed under the labelled topic | ≥ 85% |
| Needs a look | Share of emails sent to "Needs a look" | < 10% |
| Rule verdicts right | Yes or no on each labelled rule | ≥ 90% |

The report also shows:

- **Safety floor**: floor flags caught by the AI, by the word check, and by either. Word-check hits the label does not expect are listed, because the floor alerts and no rule can undo it.
- **Rules**: per rule, how often it said yes when it should not, and no when it should.
- **Slices**: the share of fully right cases per tag (`calm_urgent`, `sarcasm`, `trick`, `word_miss`, `word_false_positive`, …).
- **Routes**: label against what Herald did.
- **Quotes**: quotes must be lines from the `<email>` block (whitespace and case ignored), never from the history.
- **Summaries free of rule talk**: the summary is what the owner reads, so "the travel-soon rule does not match" is noise. This is reported on its own and does not fail a case.
- **Failing cases**: for each, the failed checks, the notes, the summary, the quotes and the rule verdicts.

A model error (rate limit, outage, bad structured output) is left out of every quality number and counted on its own line. The graph sends such an email to "Needs a look", and counting that as the AI being unsure would hide an outage.

## The test emails

Each business is one TOML file in `packages/evals/src/herald_evals/datasets/`:

- `tripfold.toml` uses the seed config (`config_ref = "herald_server.seed:TRIPFOLD"`), so the eval measures the config the product ships.
- `ledgerly.toml` is an invoicing app for freelancers, with its config inline. It exists only in the evals: the same scoring on a very different business is the proof that Herald is business agnostic.

A case is one email and its label:

```toml
[[cases]]
id = "flight-tomorrow-polite"
reviewed = false                  # true once a person agrees with the label
tags = ["calm_urgent", "rule"]
sender = "priya@example.com"
subject = "Order TF-20931 still in transit"
body = """..."""
note = "Why the label is what it is, when that is not obvious."
[cases.expect]
route = "alert"                   # or a list of routes that are all fine
topic = "Orders and delivery"     # optional, one or a list
urgency = ["urgent", "high"]      # optional
anger = [1, 2]                    # optional, a number or a range
flags = ["account_or_data"]       # the AI must add these
no_flags = ["legal_threat"]       # neither the AI nor the word check may raise these
rules = { travel-soon = true }    # only listed rules are scored
[cases.history]                   # optional: sender history, thread, corrections
```

Rules for labels:

- **Label what Herald should do for the owner**, from [product-scope.md](product-scope.md) and [decisions.md](decisions.md), not what the code does today. Where the two differ, say so in `note`.
- **Label only what the case is about.** Urgency and anger are judgement calls; leave them out or give a range.
- **Use a list of routes** when more than one is right. Such a case counts for route accuracy but not for missed alerts or false alarms.
- **`reviewed = false` until a person agrees.** Cases drafted with an AI's help start unreviewed, so the AI is not marking its own homework. The report says how many are unreviewed, and adds a hand-checked-only table once some are.
- Loading fails when a label names a rule or topic the config does not have.

## Fixing an issue

1. Run `make eval ARGS="--repeats 3"` and read the failing cases. Group them by cause (the word check, a rule's wording, the prompt, the decide order, a wrong label).
2. Fix the label first if the label is wrong, then `--rescore` the same run to see the new numbers without new model calls.
3. Change the prompt (`triage.md`), a rule, the word check or `decide`, then run the slice that failed (`--tag`, `--case`).
4. Run everything again with `--compare` on the earlier JSON. The report lists cases now right and now wrong more often. Keep the fix only if nothing important broke.
5. Add a case for every new failure you find in real mail.

The JSON records the model, the temperature, a hash of `triage.md`, each config's hash and the commit, so two runs can be told apart.
