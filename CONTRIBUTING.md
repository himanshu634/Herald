# Contributing to Herald

Thanks for helping. This file says how to propose a change. [docs/development.md](docs/development.md) says how to set up, run and test Herald.

## Before you start

- Read [docs/architecture.md](docs/architecture.md) before you change behaviour. [docs/decisions.md](docs/decisions.md) says what was decided and why. Where it differs from [docs/product-scope.md](docs/product-scope.md), `decisions.md` wins.
- For a bug, open an issue with what you did, what you expected and what happened. For an email Herald got wrong, add the email as an eval case (see [docs/evals.md](docs/evals.md)).
- For a new feature or a change to how Herald decides, open an issue first, so we can agree on the shape before you write code.

## The rules Herald keeps

A pull request that breaks one of these will not be merged, however good the rest is.

- **The AI never sets status.** It writes notes. Only `decide` and the owner's actions change an email's status.
- **No rule can silence the safety floor.** The floor runs first and runs without the AI.
- **The AI never sends mail.** Only the owner's Send button does.
- **Every tenant-owned query filters on `workspace_id`.**
- **The pipeline reaches the database only through the API's internal routes.** Nothing in `pipeline.py` or `tools/` imports `sqlmodel`.
- **Commit, then publish.** Never publish an event that is not committed.
- **Only `connectors/<provider>/` knows a mail provider.**

[CLAUDE.md](CLAUDE.md) lists these and a few more, with the files that hold each one.

## Making a change

1. Branch from `main`. Name the branch for the kind of change: `feat/alert-desk`, `fix/ai-failures`, `perf/parallel-rules`, `docs/…`.
2. Make the change, with tests. Server tests use the in-process backends and `ScriptedModel`, so they need no Docker or API key.
3. If you changed:
   - API schemas in `api/schemas.py`: run `make gen-api` and commit `schema.d.ts`.
   - Models in `models.py`: write a migration and read it (see [Database migrations](docs/development.md#database-migrations)).
   - Prompts, notes, rules or `decide`: run the evals and say what moved.
   - Behaviour: update the doc that describes it, in the same pull request.
4. Run the checks. There is no CI yet, so these are the gate:

   ```bash
   make lint
   ```

   ```bash
   make test
   ```

5. Open a pull request against `main`.

### Bigger changes

A change that spans several files or changes what Herald does gets a short spec and a plan in `docs/superpowers/specs` and `docs/superpowers/plans` before the code, dated like the others there. When the change settles a product question, add a row to the decision log in `decisions.md`: the date, the decision and why.

## Commits

One change per commit. The subject is one plain sentence in the imperative, saying what the change does for Herald, not which files it touches:

```
Retry the AI when it is down, and say why an email has no notes
Let the owner choose to have Herald read Gmail's Spam folder
Add the migration for email.in_spam and mailbox.read_spam
```

Add a body when the why is not obvious from the subject.

## Pull requests

Title: one plain sentence, like a commit subject. Body:

```markdown
## What

What changed and why, in a few bullets.

## Heads-up

Anything a reviewer or someone pulling this must know: a new env var, a migration, a changed default.

## Testing

What you ran and what it showed. Say what you did not run.

## Open items

- [ ] Follow-ups this pull request leaves.
```

Leave out a section that has nothing in it.

## Style

- **Python:** Ruff, line length 100, Python 3.13. `make format` fixes most of it.
- **Web:** Prettier with tabs, ESLint, svelte-check. Svelte 5 runes only. Import `src/lib` as `#lib/*`.
- **Design system:** components use the semantic tokens (`--color-*`, `--tone-*`), never the primitives. New components go in `src/lib/ui` and the `/design-system` gallery. See [docs/design-system.md](docs/design-system.md).
- **Comments:** comment logic that is not obvious from reading it: retries, locking, auth checks, ordering rules, parsing of outside data, anything that guards a rule above. Say why it works this way and what would break if it changed. Do not comment code that says what it does on its own.
- **Docs and copy:** short, plain sentences. No jargon the owner of a small shop would not use.

## License

Herald is MIT-licensed. By contributing, you agree that your work is released under the same [license](LICENSE).
