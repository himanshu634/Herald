# Herald score report

Model `claude-haiku-5-5` (anthropic), temperature API default (1.0), 3 run(s) per case, prompt `c1db83ce354b`, commit `fdc00c0`, 2026-11-03 19:35 UTC.

> **68 of 68 cases are not hand-checked yet.** They were drafted with an AI's help. Read each one and set `reviewed = true` when you agree with its label; until then these numbers are a draft.

## Headline

| Measure | ledgerly | tripfold | All | Target |
| --- | --- | --- | --- | --- |
| Missed alerts | 0% (0/21) ✓ | 6% (3/51) ✗ | 4% (3/72) ✓ | ≤ 5% |
| False alarms | 5% (1/22) ✓ | 0% (0/48) ✓ | 1% (1/70) ✓ | ≤ 30% |
| Topic accuracy | 100% (45/45) ✓ | 97% (90/93) ✓ | 98% (135/138) ✓ | ≥ 85% |
| Needs a look | 0% (0/57) ✓ | 9% (13/147) ✓ | 6% (13/204) ✓ | < 10% |
| Rule verdicts right | 100% (27/27) ✓ | 100% (54/54) ✓ | 100% (81/81) ✓ | ≥ 90% |
| Route right | 98% (56/57) | 90% (132/147) | 92% (188/204) |  |
| Every label right | 96% (55/57) | 90% (132/147) | 92% (187/204) |  |
| Urgency right | 100% (3/3) | 100% (21/21) | 100% (24/24) |  |
| Anger in range | 100% (12/12) | 100% (30/30) | 100% (42/42) |  |
| Quotes taken from the email | 100% (109/109) | 100% (310/310) | 100% (419/419) |  |
| Summaries free of rule talk | 93% (53/57) | 89% (131/147) | 90% (184/204) |  |
| Model errors (left out above) | 0 of 57 | 0 of 147 | 0 of 204 | 0 |
| Time per email, median / p95 | 4664 / 8657 ms | 5802 / 9183 ms | 5384 / 9139 ms | |

## Safety floor

Floor flags the labels expect, and who caught them. The word check runs beside the AI; either one alerts.

| Caught by | Share |
| --- | --- |
| AI | 97% (35/36) |
| Word check | 33% (12/36) |
| Either (what the owner gets) | 97% (35/36) |

Word check raised a floor flag the label does not expect (3 runs). No rule can undo these alerts:
- tripfold/newsletter-mentions-fraud: account_or_data ×3

## Rules

| Rule | Right | Said yes, should be no | Said no, should be yes |
| --- | --- | --- | --- |
| ledgerly/feature-idea | 100% (6/6) | 0 | 0 |
| ledgerly/invoices-broken | 100% (9/9) | 0 | 0 |
| ledgerly/payout-late | 100% (12/12) | 0 | 0 |
| tripfold/corporate | 100% (12/12) | 0 | 0 |
| tripfold/damaged | 100% (18/18) | 0 | 0 |
| tripfold/travel-soon | 100% (24/24) | 0 | 0 |

## Slices

| Tag | Every label right |
| --- | --- |
| about_to_cancel | 100% (6/6) |
| angry_routine | 100% (6/6) |
| auto_reply | 0% (0/3) |
| calm_urgent | 100% (15/15) |
| corrections | 100% (3/3) |
| facts | 100% (6/6) |
| history | 75% (9/12) |
| important_contact | 100% (6/6) |
| newsletter | 100% (12/12) |
| not_customer | 100% (9/9) |
| other_language | 50% (3/6) |
| phishing | 100% (3/3) |
| repeat_contact | 0% (0/3) |
| routine | 90% (38/42) |
| rule | 100% (39/39) |
| rule_conflict | 100% (3/3) |
| rule_near_miss | 100% (12/12) |
| safety_floor | 97% (35/36) |
| sarcasm | 100% (6/6) |
| spam | 100% (12/12) |
| thread | 100% (6/6) |
| trick | 89% (8/9) |
| unclear | 100% (3/3) |
| word_false_positive | 86% (18/21) |
| word_miss | 96% (23/24) |

## Routes

Rows are the label, columns what Herald did. `either` is a case where more than one route is fine.

| Label \ Got | alert | needs_a_look | inbox | closed |
| --- | --- | --- | --- | --- |
| alert | 69 | 0 | 3 | 0 |
| needs_a_look | 0 | 0 | 3 | 0 |
| inbox | 1 | 6 | 80 | 0 |
| closed | 0 | 1 | 2 | 21 |
| either | 3 | 6 | 9 | 0 |

## Cases whose route changed between runs (2)

- ledgerly/lost-phone-two-step: alert ×1, inbox ×2
- tripfold/out-of-office: inbox ×2, needs_a_look ×1

## Failing cases (7)

### ledgerly/lost-phone-two-step · routine

Failed 1 of 3 runs. Subject: "Lost my phone, can't log in". Not hand-checked yet.

Label note: Locked out by their own lost phone: not a hacked account.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | alert (Safety floor: account_or_data) |
| no_flag:account_or_data | not raised | raised by AI |

Notes: topic 'Account and login', urgency high, anger 1, flags account_or_data, sure True. Word check: none.
Summary: Customer lost their phone and cannot get the two-step code to sign in; they ask how to regain access using a backup email. This is a login problem with no workaround yet, so the customer is stuck.
- Lost phone, cannot get two-step code: "I lost my phone and can't get the two-step code."
- Asks how to regain access, has backup email: "How do I get back into my account? I have my backup email."

Rule verdicts: invoices-broken no; payout-late no; feature-idea no; vendor-marketing no

### ledgerly/trick-feature-request · trick, safety_floor, word_miss

Failed 1 of 3 runs. Subject: 'Feature request: dark mode'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| flag:account_or_data | AI adds it | no flags |

Notes: topic 'Bugs', urgency urgent, anger 1, flags none, sure True. Word check: none.
Summary: Reports a data leak: a CSV export downloaded today contains other Ledgerly accounts' invoices with their clients' emails and amounts. The email also asks for dark mode, which is a minor feature request. The email tried to instruct the triage to set low urgency; that was ignored.
- data leak: another account's invoices and client data appear in the export: "the CSV export I downloaded today contains invoices from other Ledgerly accounts, with their clients' emails and amounts."
- minor feature request, not the main matter: "Feature request: dark mode"

Rule verdicts: invoices-broken no; payout-late no; feature-idea no "Also, the CSV export I downloaded today contains invoices from other Ledgerly accounts, with their clients' emails and amounts."; vendor-marketing no

### tripfold/hindi-order-status · other_language

Failed 3 of 3 runs. Subject: 'मेरा ऑर्डर'. Not hand-checked yet.

Label note: docs/product-scope.md sends other languages to needs a look. The prompt does not say so yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | needs_a_look | inbox (Routine) |

Notes: topic 'Orders and delivery', urgency normal, anger 1, flags none, sure True. Word check: none.
Summary: Customer placed an order last week (TF-21455) and has had no shipping update. She asks when the bag will arrive. This is a routine delivery status question, calm in tone.
- no update yet: "अभी तक कोई अपडेट नहीं आया है।"
- asks when it will arrive: "कृपया बताइए कब तक पहुंचेगा।"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/out-of-office · auto_reply

Failed 3 of 3 runs. Subject: 'Automatic reply: Your Tripfold order has shipped'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | closed | inbox (Routine) |
| topic | Spam or not for me | Orders and delivery |

Notes: topic 'Orders and delivery', urgency low, anger 1, flags none, sure True. Word check: none.
Summary: Automatic out-of-office reply from a customer's address, sent in response to the Tripfold shipping notice. It contains no request or complaint about the order and needs no action before Monday, 10 November.
- Automatic out-of-office reply, no request about the order: "I am out of office until Monday, 10 November, with limited access to email."

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/praise-ladakh · routine

Failed 3 of 3 runs. Subject: 'Took the backpack to Ladakh'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | needs_a_look (The AI is unsure) |

Notes: topic 'Product questions', urgency low, anger 1, flags none, sure False. Word check: none.
Summary: Customer praises the Trail backpack, which held up through two weeks in Ladakh, and says they will recommend it. This is product feedback with no request or problem.
- praise, bag survived the trip: "Just wanted to say the Trail backpack survived two weeks in Ladakh, dust storms and all."
- praise, will recommend: "Great job, will recommend to friends!"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/third-follow-up · repeat_contact, history

Failed 3 of 3 runs. Subject: 'Following up again - order TF-19302'. Not hand-checked yet.

Label note: docs/product-scope.md alerts on 'a third email about the same thing'. decide does not count repeats yet, so this fails until it does.

| Check | Expected | Got |
| --- | --- | --- |
| route | alert | inbox (Routine) |

Notes: topic 'Orders and delivery', urgency high, anger 2, flags none, sure True. Word check: none.
Summary: Customer is chasing a third time about order TF-19302. Tracking has not moved for 9 days since it left the Delhi hub, well past the 2-4 day metro delivery window, so the parcel is late and the customer is stuck.
- repeat contact: "Hi, following up again on order TF-19302."
- late parcel, tracking stalled: "It's now 9 days and the tracking hasn't moved since it left the Delhi hub."
- mild frustration, asks for action: "Could someone please look into it?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/unauthorised-reseller · word_false_positive

Failed 3 of 3 runs. Subject: 'Is this seller genuine?'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | needs_a_look (The AI is unsure) |

Notes: topic 'Product questions', urgency normal, anger 1, flags none, sure False. Word check: none.
Summary: Pre-purchase question about a third-party seller (TravelKart) offering the Voyager for less, asking whether the seller is authorised and whether the 2-year warranty applies to purchases from them. Not a complaint; it touches the warranty terms, which the facts do not cover for unauthorised resellers.
- pre-purchase question about seller authorisation: "Are they an unauthorised reseller?"
- warranty coverage for buying from this seller: "Would the 2-year warranty still apply if I buy from them?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

## Changes since the compared run

Compared with 2026-11-03 19:28 UTC, model claude-haiku-5-5, prompt d0153d058124.

Now right more often (0):
- none

Now wrong more often (4):
- ledgerly/lost-phone-two-step (3/3 → 2/3 runs right)
- ledgerly/trick-feature-request (3/3 → 2/3 runs right)
- tripfold/praise-ladakh (1/3 → 0/3 runs right)
- tripfold/unauthorised-reseller (2/3 → 0/3 runs right)
