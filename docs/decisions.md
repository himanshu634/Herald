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
| 2026-11-03 | **Notes are trimmed.** The "going public" / "abusive" flags are cut for now. Repeat contact is not a note: code counts it from history (`email.context` `repeat_7d` / `repeat_30d`). | Counting is exact in code, and threads now exist through `thread_id`. |
| 2026-11-04 | **The third email about the same thing alerts.** `decide` counts it in code from sender history: this email plus at least two earlier ones from the same sender, on the same topic, in the 7 days before it, that are not done or closed. It sits with the other alert defaults, after the rules. Sender history now carries `as_of` (when the current email arrived) to place the window; without it nothing counts. | product-scope promised this alert and nothing implemented it; the evals' `third-follow-up` case missed it on every run. Counting stays exact in code, as the "Notes are trimmed" decision says. Done and closed emails end a matter, so a customer with several separate questions is not a chase. |
| 2026-11-03 | **Stack: SvelteKit (Svelte 5) + FastAPI + LangGraph, with Postgres and Redis.** FastAPI streams events to the browser over SSE. Details in [architecture.md](architecture.md). | Chosen by the owner of this repo. |
| 2026-11-03 | **Mail connectors are provider-neutral; Gmail is the first.** One `Mailbox` table and one sync job serve every provider; provider details live in the connector and its opaque cursor. | Outlook and IMAP can be added later without changing tables or routes. |
| 2026-11-03 | **Owner guidance goes in the business block of the prompt.** Plain lines that shape topic, urgency and anger. They are fenced so they cannot silence the safety floor. Routing stays with rules. | Owners know things about their business that are not when/then rules ("wedding planners matter most"). |
| 2026-11-03 | **Agent tools run in code before the model reads the email (pre-fetch), not in a model loop.** | The history needed is the same for every email, so a loop would add cost and delay for no gain. It keeps `word_check` and `decide` unaffected, and a failed tool cannot stall triage. |
| 2026-11-03 | **History comes from Herald's database, never from the mail provider.** | It is fast and needs no extra mail scope. Every row already carries `workspace_id`, so the tools stay inside one tenant. |
| 2026-11-03 | **Setup is drafted by the AI from the business description**, then edited by the owner. This replaces starter templates. | One description gives a sensible first draft for any business, with no template catalogue to maintain. |
| 2026-11-03 | **One business per mailbox.** A connected mailbox belongs to exactly one workspace. Enforced: `(provider, email_address)` is unique across workspaces for every mailbox that is not disconnected (the connect answers `mailbox_in_use`). | A mailbox's mail is triaged under exactly one business's rules. |
| 2026-11-03 | **One Claude call per email.** For now two calls (`write_notes`, `judge_rules`) share one cached system prompt. | The prompt is written for the single call, so merging the calls later changes only the output schema. |
| 2026-11-03 | **Facts are kept apart from guidance.** Facts say what is true ("returns within 7 days"). Guidance says how to judge ("wedding orders are always urgent"). | Guidance stays fenced so it cannot silence the safety floor. Facts need no fence. Setup drafts facts only from the owner's description, because a made-up policy would be worse than none. |
| 2026-11-03 | **The contact list stays out of the prompt.** Code adds an "(important contact)" marker to the email. | The list would make the prompt longer and show one customer's address in every other customer's call. |
| 2026-11-03 | **The general instructions are in `triage.md`, not API Agent Skills.** | Agent Skills need a code-execution container on every request, Claude loads a skill only when it judges the task needs it, and they add tool round trips before Claude reads the email. Triage needs the same instructions on every email, in one call. |
| 2026-11-03 | **The default model is Claude Haiku 5.5** (`claude-haiku-5-5`), not Opus 5.5. `HERALD_MODEL_NAME` still picks another model. | Every email waits on the model, so it sets triage latency and cost. Revisit with the test-email set and the score report. |
| 2026-11-04 | **Mail that is not about the business closes before the owner's rules and the defaults.** Only the safety floor comes first. It applies when the AI files the email under "Spam or not for me", is sure, and the sender is not an important contact; rules are not judged for it. "Not for me" means not about this business's products, orders, customers or partners: a supplier, courier or journalist writing about the business is not spam. | Promotions and newsletters were alerting through rules ("Going public") and defaults ("sale ends today" read as urgent). A correct spam verdict could not win. The floor stays absolute, so a newsletter that matches the word check still alerts. |
| 2026-11-03 | **A business with no mailbox stays closed.** Until a mailbox is connected (in any status but `disconnected`), the web shows only the Connect Gmail screen: no inbox and no test-email box. The seeded demo (`workspace.demo`) is the one exception. | A real business is about its own customers' mail. An inbox that can never fill only misleads; the demo exists so Herald can be tried without a mailbox. |
| 2026-11-04 | **Emails no rule covers are judged from the setup.** The prompt tells Claude the facts, guidance and rules are not a full list. It judges a new kind of email as the owner would, and puts that into topic, urgency and summary. Rule verdicts do not stretch: an email that is only like a rule's case is a no. When it cannot tell, `sure` is false. | New situations keep coming. Owners should not need a rule for each one. Stretching a verdict could fire a hidden close rule and bury a real email, so the judgement goes into the notes, where `decide` still routes it. |
| 2026-11-04 | **When Herald is unsure, it asks one question, above every view.** Unsure notes carry a `question` and an optional `fact_draft`. The inbox pins every unsure email the owner has not taken over above the tabs and filters, and the owner answers in a dialog by adding or changing a fact. Saving re-reads the email. The draft is never saved on its own. | An unsure email hid behind filters, or in Closed quietly when a close rule won first, and the owner had no way to answer it. A fact fixes the next email of the same kind too. A made-up policy would be worse than none, so the owner checks the draft. |

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
