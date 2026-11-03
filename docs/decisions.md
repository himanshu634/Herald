# Herald: Scoping Decisions

Herald ships as a multi-tenant framework, and the demo shows one business: Tripfold, a made-up online luggage brand. These decisions narrow [product-scope.md](product-scope.md); where the two differ, this file wins.

## Decision log

| Date | Decision | Why |
| --- | --- | --- |
| 2026-11-03 | **Herald is a multi-tenant framework, not an app for one company.** Each business is a workspace. Its profile, topics, contacts and rules are data. | Many businesses use the same product. Adding one is an API call, not new code. |
| 2026-11-03 | **The demo ships one business: Tripfold**, an online luggage and travel-bag brand modelled on brands like Mokobara. | Keeps the build small. Using a made-up name avoids presenting a real company's data. |
| 2026-11-03 | **No starter templates.** With one demo business there is nothing to choose between. Setup (profile, topics, contacts, rules) stays. | Setup is what keeps the product general. |
| 2026-11-03 | **One kind of rule.** "When" is plain text the AI judges, answering yes or no with a quote. "Then" is one of three actions: alert me, set urgency, close quietly. | Drops the split between exact checks and judgement checks, and with it a rule parser. Facts about senders go in Important contacts. |
| 2026-11-03 | **The decide step is plain Python, with no AI.** Order: safety floor, then the owner's rules, then the defaults. | "The AI suggests, rules decide" is enforced in the code. The notes type has no status field. |
| 2026-11-03 | **A safety floor no rule can switch off.** It covers safety, a hacked account or data leak, and legal threats. A word check runs beside the AI. | One AI mistake, or an email written to trick it, cannot bury a real threat. |
| 2026-11-03 | **Alerts stay in the app.** An alerted email goes to the top of the inbox and SSE sends `alert.sent` to open tabs. Nothing is pushed to a phone or any outside service. | The owner does not want alerts sent outside the app. This replaces the earlier plan to push alerts to the phone first. |
| 2026-11-03 | **Notes are trimmed.** Repeat contact and "going public" / "abusive" flags are cut for now. | Repeat contact needs customer identity and threads. |
| 2026-11-03 | **Stack: SvelteKit (Svelte 5) + FastAPI + LangGraph, with Postgres and Redis.** FastAPI streams events to the browser over SSE. Details in [architecture.md](architecture.md). | Chosen by the owner of this repo. |
| 2026-11-03 | **Mail connectors are provider-neutral; Gmail is the first.** One `Mailbox` table and one sync job serve every provider; provider details live in the connector and its opaque cursor. | Outlook and IMAP can be added later without changing tables or routes. |
| 2026-11-03 | **Owner guidance goes in the business block of the prompt.** Plain lines that shape topic, urgency and anger. They are fenced so they cannot silence the safety floor. Routing stays with rules. | Owners know things about their business that are not when/then rules ("wedding planners matter most"). |
| 2026-11-03 | **Setup is drafted by the AI from the business description**, then edited by the owner. This replaces starter templates. | One description gives a sensible first draft for any business, with no template catalogue to maintain. |
| 2026-11-03 | **One business per mailbox.** A connected mailbox belongs to exactly one workspace. Enforced: `(provider, email_address)` is unique across workspaces for every mailbox that is not disconnected (the connect answers `mailbox_in_use`). | A mailbox's mail is triaged under exactly one business's rules. |
| 2026-11-03 | **One Claude call per email.** For now two calls (`write_notes`, `judge_rules`) share one cached system prompt. | The prompt is written for the single call, so merging the calls later changes only the output schema. |
| 2026-11-03 | **Facts are kept apart from guidance.** Facts say what is true ("returns within 7 days"). Guidance says how to judge ("wedding orders are always urgent"). | Guidance stays fenced so it cannot silence the safety floor. Facts need no fence. Setup drafts facts only from the owner's description, because a made-up policy would be worse than none. |
| 2026-11-03 | **The contact list stays out of the prompt.** Code adds an "(important contact)" marker to the email. | The list would make the prompt longer and show one customer's address in every other customer's call. |
| 2026-11-03 | **The general instructions are in `triage.md`, not API Agent Skills.** | Agent Skills need a code-execution container on every request, Claude loads a skill only when it judges the task needs it, and they add tool round trips before Claude reads the email. Triage needs the same instructions on every email, in one call. |
| 2026-11-03 | **The default model is Claude Haiku 5.5** (`claude-haiku-5-5`), not Opus 5.5. `HERALD_MODEL_NAME` still picks another model. | Every email waits on the model, so it sets triage latency and cost. Revisit with the test-email set and the score report. |

## Cuts

| Area | In the build | Cut or parked |
| --- | --- | --- |
| Businesses | Tripfold only, as seed data | A second business and starter templates |
| Rules | Plain-text "when" + three actions, tested on past emails | Exact checks, "set topic" and "mark important" actions |
| Alerts | In the web app only: summary, quote and rule on the alerted email, with its actions | Phone or other outside alerts, quiet hours, reminders, morning summary |
| Notes | Topic, urgency, anger, floor flags + about to cancel, summary with quotes, sure or unsure | Repeat contact, going public, abusive |
| Quality | About 30 hand-checked test emails and one score report | 50–70 emails per business across three businesses |
| Differentiators | At most one: past corrections fed back to the AI as examples | Rule suggestions, overview, thread awareness |

## Open questions

- [ ] Time budget and deadline. The plan assumes about 5 days.
- [ ] Hosted platform or a library that developers install? The build assumes hosted.
- [ ] Which AI providers are allowed, and is there a cost ceiling? The build defaults to Claude, with an offline fake model.
- [ ] Is a hosted demo expected, or a repo the reviewers run locally?
