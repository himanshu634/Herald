# Plan: triage only mail about the business

Promotions, newsletters and other mail that is not about the business reach the owner's
triage. They should close quietly and stay findable.

## What the research found

**The pipeline does have a "not for us" verdict, but it can't win.** The AI can file an
email under `SPAM_TOPIC` ("Spam or not for me"), and `decide` closes it only at step 6. By
then four other checks have had a chance to alert:

1. Owner alert rules (step 2). They also beat owner close rules.
2. Urgent (step 3). "Sale ends today" reads as urgent.
3. Anger 5 (step 3).
4. `about_to_cancel` (step 4). "Cancel anytime" reads as a customer about to cancel.

`judge_rules` also runs every owner rule on every email. Rules written as "The customer
says…" are judged against newsletters.

**Evidence from the local Postgres (Stride & Stitch workspace):**

| Email | Topic | What fired | Result |
| --- | --- | --- | --- |
| Substack newsletter | Spam or not for me | alert rule "Going public" | Alerted; the owner corrected it to inbox |
| Adobe "SALE IS LIVE" | Spam or not for me | alert rule "Going public" | Alerted; corrected |
| Business Standard epaper | Orders and delivery | alert "Stockist shipment problem" beat close "Newsletters and promotions" | Alerted; corrected |
| Hello Interview newsletter | Questions | alert rule "Third email, same order" | Alerted; corrected |

Caveat: these rows came from `FakeModel`. `HERALD_MODEL_PROVIDER` is unset in `.env`, so it
defaults to `fake`, whose keyword rule judge fires on any shared 6+ letter word. The rows
don't measure how well Claude classifies mail. They do prove the ordering bug: a spam
verdict, even with a close rule firing, still lost to an alert rule.

**Side effects:**

- **Bad corrections.** Each "Not urgent" correction now teaches the model "a newsletter
  belongs in the inbox". These corrections feed `recent_corrections`.
- **No way out of Closed.** `actionsFor('closed')` returns no actions. If more mail closes,
  a customer email the AI files wrong cannot be moved back.
- **Word check on newsletters.** `word_check` (the safety floor) matches "court", "fraud" and
  "hacked" in news mail, so a daily newspaper can alert. The floor stays absolute (see
  "Decided" below).
- **Unused signals.** Gmail already sends `CATEGORY_PROMOTIONS` / `CATEGORY_SOCIAL` in
  `label_ids`. The raw message carries `List-Unsubscribe`, `List-Id`, `Precedence` and
  `Auto-Submitted`. `mime.py` drops all of them.

## Phase 1: let a sure "not for us" verdict win (one PR, no schema change, no DB reset)

1. **One helper for the condition** (`herald_core/decide.py`), for example
   `is_not_for_business(notes, config, sender)`. It is true when all three hold:
   - the topic is `SPAM_TOPIC`. Compare after casefold and strip, because `Notes.topic` is a
     free string.
   - `notes.sure` is true.
   - the sender is not an important contact (`config.is_important`).

   `decide` and the graph both call it, so the two can't drift apart. If they did, an
   important contact's email could get no verdicts and no close.
2. **`decide` order** becomes:
   1. Safety floor.
   2. Not for the business → closed (new).
   3. Owner rules.
   4. Urgent or anger 5.
   5. Anger 4 from an important contact, or about to cancel.
   6. Unsure → needs a look.
   7. Spam → closed. This stays for the cases the helper excludes: an important contact's
      spam email after the rules and defaults.
   8. Inbox.

   An unsure spam verdict keeps today's path, so it reaches "needs a look". Update the
   docstring.
3. **`graph.judge_rules`** returns `{"verdicts": []}` when the helper is true. This saves one
   Claude call per promotion. The node already skips when the notes are `None`.
4. **`prompts/triage.md`:** define "Spam or not for me" by whether the mail is *about this
   business*, not by whether a customer sent it.
   - Spam: promotions and newsletters sent to the owner, cold sales pitches, social and app
     notifications, personal mail, phishing.
   - Not spam: a supplier, stockist, courier, payment provider or the press writing about
     this business. Owner rules such as "Stockist shipment problem" and "Press and
     collaborations" depend on that mail.
   - A catch-all topic ("Questions: anything that fits no other topic") is only for real mail
     to the business. Setup's fallback and the fake drafter both create one.
   - Risk flags describe the sender's own situation, not news or ads quoted in the email.

   No placeholders, and the prompt still names every urgency and flag (`test_prompt`).
5. **`FakeModel`:** widen the spam guess beyond "unsubscribe" (for example "newsletter",
   "view in browser", "% off", "sale"), so tests and lite mode show the new behaviour.
6. **Tests:**
   - `test_decide`: sure spam closes ahead of an alert rule, urgent, anger 5 and
     about-to-cancel. Unsure spam goes to needs a look. Important-contact spam is not closed
     early. The floor still alerts on spam.
   - `test_graph`: turn the real subjects above into cases. Rules are not judged for a sure
     spam email.
   - Loose topic match: `"spam or not for me "` closes.
7. **Docs:**
   - `decisions.md`: a new row ("Mail not about the business closes before rules and
     defaults; only the safety floor comes first").
   - `architecture.md`: the decide order and the pipeline note.
   - `product-scope.md`: the order table (`decisions.md` wins over it anyway).

**Done when:** `make test` and `make lint` pass, and the four emails above, run again in lite
mode, close with reason "Spam or not for me".

## Phase 2: move a misfiled email out of Closed (small PR, needed once Phase 1 closes more)

- A new owner action "Not for me? Move to inbox": `POST .../emails/{id}/to-inbox`, allowed
  only from `closed`. It records a `Correction` (`field="route"`, `closed → inbox`), so
  `recent_corrections` gets a real "this is business mail" example.
- Web: `actionsFor('closed')` gains the action. Run `make gen-api`.

## Phase 3: deterministic mail signals (separate PR, needs a DB reset)

- `connectors/gmail/` maps labels and headers to provider-neutral signals on
  `InboundMessage`: `bulk` (List-Unsubscribe, List-Id, Precedence bulk or list, Gmail
  Promotions or Social) and `auto_reply` (Auto-Submitted, X-Autoreply). Only the Gmail
  connector knows Gmail names.
- A new `Email.signals` JSON column, `core.Email.signals`, and one line in `email_block`
  ("Mail signals: bulk mail"). It goes in the user message, so the system prompt cache is
  untouched.
- Signals are a hint, never a close on their own: anyone can add these headers, and Gmail
  sometimes misfiles real mail.
- No migrations, so every dev DB must be reset: delete `herald-dev.db`, or run
  `docker compose … down -v`.

## Decided: the safety floor stays absolute

On 2026-11-04 the owner chose to keep the floor as it is. A newsletter that matches the word
check (for example "court" or "fraud") still alerts. The floor runs before the new "not for
the business" check, and nothing in this plan changes it.

## Out of scope

- Re-triaging emails already stored. The four wrong corrections in dev can be deleted by
  hand.
- Skipping the AI entirely for bulk mail. Phase 1 already saves the `judge_rules` call.
  Revisit after the score report.
