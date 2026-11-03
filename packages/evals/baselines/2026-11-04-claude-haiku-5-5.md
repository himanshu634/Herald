# Herald score report

Model `claude-haiku-5-5` (anthropic), temperature API default (1.0), 3 run(s) per case, prompt `c1db83ce354b`, commit `31202ce`, 2026-11-03 19:44 UTC.

> **69 of 69 cases are not hand-checked yet.** They were drafted with an AI's help. Read each one and set `reviewed = true` when you agree with its label; until then these numbers are a draft.

## Headline

| Measure | ledgerly | tripfold | All | Target |
| --- | --- | --- | --- | --- |
| Missed alerts | 0% (0/21) ✓ | 4% (2/51) ✓ | 3% (2/72) ✓ | ≤ 5% |
| False alarms | 0% (0/21) ✓ | 0% (0/49) ✓ | 0% (0/70) ✓ | ≤ 30% |
| Topic accuracy | 100% (45/45) ✓ | 97% (93/96) ✓ | 98% (138/141) ✓ | ≥ 85% |
| Needs a look | 0% (0/57) ✓ | 11% (16/150) ✗ | 8% (16/207) ✓ | < 10% |
| Rule verdicts right | 100% (27/27) ✓ | 100% (54/54) ✓ | 100% (81/81) ✓ | ≥ 90% |
| Route right | 100% (57/57) | 89% (134/150) | 92% (191/207) |  |
| Every label right | 100% (57/57) | 89% (134/150) | 92% (191/207) |  |
| Urgency right | 100% (3/3) | 90% (19/21) | 92% (22/24) |  |
| Anger in range | 100% (12/12) | 100% (30/30) | 100% (42/42) |  |
| Quotes taken from the email | 100% (109/109) | 100% (325/325) | 100% (434/434) |  |
| Summaries free of rule talk | 88% (50/57) | 85% (127/150) | 86% (177/207) |  |
| Model errors (left out above) | 0 of 57 | 0 of 150 | 0 of 207 | 0 |
| Time per email, median / p95 | 4676 / 8956 ms | 5440 / 9110 ms | 5162 / 9095 ms | |

## Safety floor

Floor flags the labels expect, and who caught them. The word check runs beside the AI; either one alerts.

| Caught by | Share |
| --- | --- |
| AI | 100% (36/36) |
| Word check | 33% (12/36) |
| Either (what the owner gets) | 100% (36/36) |

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
| calm_urgent | 87% (13/15) |
| corrections | 100% (3/3) |
| facts | 100% (6/6) |
| history | 100% (15/15) |
| important_contact | 100% (6/6) |
| newsletter | 100% (12/12) |
| not_customer | 100% (9/9) |
| other_language | 50% (3/6) |
| phishing | 100% (3/3) |
| repeat_contact | 100% (6/6) |
| routine | 93% (39/42) |
| rule | 95% (37/39) |
| rule_conflict | 33% (1/3) |
| rule_near_miss | 83% (10/12) |
| safety_floor | 100% (36/36) |
| sarcasm | 100% (6/6) |
| spam | 100% (12/12) |
| thread | 100% (6/6) |
| trick | 100% (9/9) |
| unclear | 100% (3/3) |
| word_false_positive | 86% (18/21) |
| word_miss | 100% (24/24) |

## Routes

Rows are the label, columns what Herald did. `either` is a case where more than one route is fine.

| Label \ Got | alert | needs_a_look | inbox | closed |
| --- | --- | --- | --- | --- |
| alert | 70 | 1 | 1 | 0 |
| needs_a_look | 0 | 0 | 3 | 0 |
| inbox | 0 | 8 | 82 | 0 |
| closed | 0 | 1 | 2 | 21 |
| either | 3 | 6 | 9 | 0 |

## Cases whose route changed between runs (3)

- tripfold/airport-handle-snapped: inbox ×1, needs_a_look ×1, alert ×1
- tripfold/flight-tomorrow-bag-arrived: needs_a_look ×2, inbox ×1
- tripfold/out-of-office: inbox ×2, needs_a_look ×1

## Failing cases (6)

### tripfold/airport-handle-snapped · calm_urgent, rule, rule_conflict

Failed 2 of 3 runs. Subject: 'Handle broke at the airport'. Not hand-checked yet.

Label note: The profile names this exact bad day. The `damaged` rule sets urgency to high, which can override the AI's urgent and stop the alert: the label is alert because the owner would want to know.

| Check | Expected | Got |
| --- | --- | --- |
| route | alert | inbox (Routine) |
| urgency | urgent | high |

Notes: topic 'Damaged or defective', urgency high, anger 2, flags none, sure True. Word check: none.
Summary: Customer at Bengaluru airport says the telescopic handle on a Tripfold Voyager snapped off at check-in, so the 23 kg bag cannot be moved through the terminal. He has a connecting flight in Delhi, boards in two hours, and asks what can be done. The bag arrived last month, so this is a breakage during use that needs same-day help.
- damaged rule: bag broke during use: "the telescopic handle on my Tripfold Voyager just snapped off at check-in"
- high urgency: stuck with no workaround, boards soon: "I board in two hours."
- stuck with no workaround: "can't drag a 23 kg bag through the terminal like this"
- mild frustration, asks for help: "What can you do?"

Rule verdicts: travel-soon no; damaged yes "the telescopic handle on my Tripfold Voyager just snapped off at check-in"; corporate no; newsletters no

### tripfold/flight-tomorrow-bag-arrived · rule_near_miss

Failed 2 of 3 runs. Subject: "Cabin size check before tomorrow's flight". Not hand-checked yet.

Label note: Travelling tomorrow, but the order has arrived, so the travel rule does not match.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | needs_a_look (The AI is unsure) |

Notes: topic 'Product questions', urgency normal, anger 1, flags none, sure False. Word check: none.
Summary: Customer asks whether the Aero cabin bag fits IndiGo's 55 x 35 x 25 cm and 7 kg limit with the expander closed. It is a real product question about sizes and airline cabin limits, sent before buying-style use, and the flight is tomorrow but the bag has already arrived, so it can wait for today's session.
- Product question about airline cabin limits: "Will the bag fit when the expander is closed?"
- Bag already arrived, so no delivery problem: "My Aero cabin bag arrived yesterday, thank you!"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/hindi-order-status · other_language

Failed 3 of 3 runs. Subject: 'मेरा ऑर्डर'. Not hand-checked yet.

Label note: docs/product-scope.md sends other languages to needs a look. The prompt does not say so yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | needs_a_look | inbox (Routine) |
| summary | about the email, not the rules | Customer ordered a bag last week (order TF-21455) and has had no update yet. She asks when it will arrive. This is a routine delivery status question. Nothing says she is travelling within 48 hours, so the travel-soon rule does not match. |

Notes: topic 'Orders and delivery', urgency normal, anger 1, flags none, sure True. Word check: none.
Summary: Customer ordered a bag last week (order TF-21455) and has had no update yet. She asks when it will arrive. This is a routine delivery status question. Nothing says she is travelling within 48 hours, so the travel-soon rule does not match.
- No update on the order yet: "अभी तक कोई अपडेट नहीं आया है।"
- Asks for delivery date: "कृपया बताइए कब तक पहुंचेगा।"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/out-of-office · auto_reply

Failed 3 of 3 runs. Subject: 'Automatic reply: Your Tripfold order has shipped'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | closed | inbox (Routine) |
| topic | Spam or not for me | Orders and delivery |

Notes: topic 'Orders and delivery', urgency low, anger 1, flags none, sure True. Word check: none.
Summary: Out-of-office auto-reply from a contact at Brightline Partners, sent in response to a Tripfold order shipped notice. It is about an order but asks for nothing and reports no problem, so no action is needed. The sender is away until Monday, 10 November, and names a colleague for urgent matters.
- Order subject: "Automatic reply: Your Tripfold order has shipped"
- Out of office, no action needed: "I am out of office until Monday, 10 November, with limited access to email."

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/praise-ladakh · routine

Failed 3 of 3 runs. Subject: 'Took the backpack to Ladakh'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | needs_a_look (The AI is unsure) |

Notes: topic 'Product questions', urgency low, anger 1, flags none, sure False. Word check: none.
Summary: Customer praise about the Trail backpack after two weeks in Ladakh, with a promise to recommend it to friends. This is product feedback, not a question, and no listed topic is for feedback.
- praise of product durability: "Just wanted to say the Trail backpack survived two weeks in Ladakh, dust storms and all."
- positive referral intent: "Great job, will recommend to friends!"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/unauthorised-reseller · word_false_positive

Failed 3 of 3 runs. Subject: 'Is this seller genuine?'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | needs_a_look (The AI is unsure) |

Notes: topic 'Product questions', urgency normal, anger 1, flags none, sure False. Word check: none.
Summary: Pre-purchase question from a customer considering the Voyager bag on TravelKart, a third-party site at a lower price. They ask whether the seller is an authorised reseller and whether the 2-year warranty applies to a purchase from them. The facts cover the warranty but not warranty cover for unauthorised resellers, so the owner needs to confirm the policy.
- Price-led purchase from a third-party site: "I found the Voyager for ₹3,000 less on a site called TravelKart."
- Asks whether the seller is authorised: "Are they an unauthorised reseller?"
- Asks whether warranty covers this purchase: "Would the 2-year warranty still apply if I buy from them?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

## Changes since the compared run

Compared with 2026-11-03 19:35 UTC, model claude-haiku-5-5, prompt c1db83ce354b.

Now right more often (3):
- ledgerly/lost-phone-two-step (2/3 → 3/3 runs right)
- ledgerly/trick-feature-request (2/3 → 3/3 runs right)
- tripfold/third-follow-up (0/3 → 3/3 runs right)

Now wrong more often (2):
- tripfold/airport-handle-snapped (3/3 → 1/3 runs right)
- tripfold/flight-tomorrow-bag-arrived (3/3 → 1/3 runs right)
