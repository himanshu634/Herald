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
| 2026-11-03 | **One push channel first: ntfy.** SSE reaches only an open tab, so alerts also need a push to the phone. | Least work for a real phone buzz. Notifier is an interface, so Web Push or Slack can be added later. |
| 2026-11-03 | **Notes are trimmed.** Repeat contact and "going public" / "abusive" flags are cut for now. | Repeat contact needs customer identity and threads. |
| 2026-11-03 | **Stack: SvelteKit (Svelte 5) + FastAPI + LangGraph, with Postgres and Redis.** FastAPI streams events to the browser over SSE. Details in [architecture.md](architecture.md). | Chosen by the owner of this repo. |
| 2026-11-03 | **Owner guidance goes in the notes prompt.** Plain lines that shape topic, urgency and anger. They are fenced so they cannot silence the safety floor. Routing stays with rules. | Owners know things about their business that are not when/then rules ("wedding planners matter most"). |
| 2026-11-03 | **Setup is drafted by the AI from the business description**, then edited by the owner. This replaces starter templates. | One description gives a sensible first draft for any business, with no template catalogue to maintain. |
| 2026-11-03 | **One business per mailbox.** A connected mailbox belongs to exactly one workspace. Open item: the mail-connectors work must make `(provider, email_address)` unique. | A mailbox's mail is triaged under exactly one business's rules. |
| 2026-11-03 | **The default model is Claude Haiku 5.5** (`claude-haiku-5-5`), not Opus 5.5. `HERALD_MODEL_NAME` still picks another model. | Every email waits on the model, so it sets triage latency and cost. Revisit with the test-email set and the score report. |

## Cuts

| Area | In the build | Cut or parked |
| --- | --- | --- |
| Businesses | Tripfold only, as seed data | A second business and starter templates |
| Rules | Plain-text "when" + three actions, tested on past emails | Exact checks, "set topic" and "mark important" actions |
| Alerts | ntfy push with summary, quote and rule; actions in the web app | Answering from the phone, quiet hours, reminders, morning summary |
| Notes | Topic, urgency, anger, floor flags + about to cancel, summary with quotes, sure or unsure | Repeat contact, going public, abusive |
| Quality | About 30 hand-checked test emails and one score report | 50–70 emails per business across three businesses |
| Differentiators | At most one: past corrections fed back to the AI as examples | Rule suggestions, overview, thread awareness |

## Open questions

- [ ] Time budget and deadline. The plan assumes about 5 days.
- [ ] Hosted platform or a library that developers install? The build assumes hosted.
- [ ] Which AI providers are allowed, and is there a cost ceiling? The build defaults to Claude, with an offline fake model.
- [ ] Is a hosted demo expected, or a repo the reviewers run locally?
