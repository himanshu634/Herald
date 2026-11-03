# Herald score report

Model `claude-haiku-5-5` (anthropic), temperature API default (1.0), 3 run(s) per case, prompt `d0153d058124`, commit `9a79d14`, 2026-11-03 19:28 UTC.

> **68 of 68 cases are not hand-checked yet.** They were drafted with an AI's help. Read each one and set `reviewed = true` when you agree with its label; until then these numbers are a draft.

## Headline

| Measure | ledgerly | tripfold | All | Target |
| --- | --- | --- | --- | --- |
| Missed alerts | 0% (0/21) ✓ | 6% (3/51) ✗ | 4% (3/72) ✓ | ≤ 5% |
| False alarms | 0% (0/21) ✓ | 0% (0/48) ✓ | 0% (0/69) ✓ | ≤ 30% |
| Topic accuracy | 100% (45/45) ✓ | 97% (90/93) ✓ | 98% (135/138) ✓ | ≥ 85% |
| Needs a look | 0% (0/57) ✓ | 7% (10/147) ✓ | 5% (10/204) ✓ | < 10% |
| Rule verdicts right | 100% (27/27) ✓ | 100% (54/54) ✓ | 100% (81/81) ✓ | ≥ 90% |
| Route right | 100% (57/57) | 92% (135/147) | 94% (192/204) |  |
| Every label right | 100% (57/57) | 92% (135/147) | 94% (192/204) |  |
| Urgency right | 100% (3/3) | 100% (21/21) | 100% (24/24) |  |
| Anger in range | 100% (12/12) | 100% (30/30) | 100% (42/42) |  |
| Quotes taken from the email | 100% (113/113) | 100% (353/353) | 100% (466/466) |  |
| Summaries free of rule talk | 68% (39/57) | 67% (99/147) | 68% (138/204) |  |
| Model errors (left out above) | 0 of 57 | 0 of 147 | 0 of 204 | 0 |
| Time per email, median / p95 | 5707 / 7821 ms | 5881 / 8327 ms | 5830 / 8327 ms | |

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
| routine | 95% (40/42) |
| rule | 100% (39/39) |
| rule_conflict | 100% (3/3) |
| rule_near_miss | 100% (12/12) |
| safety_floor | 100% (36/36) |
| sarcasm | 100% (6/6) |
| spam | 100% (12/12) |
| thread | 100% (6/6) |
| trick | 100% (9/9) |
| unclear | 100% (3/3) |
| word_false_positive | 95% (20/21) |
| word_miss | 100% (24/24) |

## Routes

Rows are the label, columns what Herald did. `either` is a case where more than one route is fine.

| Label \ Got | alert | needs_a_look | inbox | closed |
| --- | --- | --- | --- | --- |
| alert | 69 | 0 | 3 | 0 |
| needs_a_look | 0 | 0 | 3 | 0 |
| inbox | 0 | 3 | 84 | 0 |
| closed | 0 | 1 | 2 | 21 |
| either | 3 | 6 | 9 | 0 |

## Cases whose route changed between runs (3)

- tripfold/out-of-office: needs_a_look ×1, inbox ×2
- tripfold/praise-ladakh: needs_a_look ×2, inbox ×1
- tripfold/unauthorised-reseller: inbox ×2, needs_a_look ×1

## Failing cases (5)

### tripfold/hindi-order-status · other_language

Failed 3 of 3 runs. Subject: 'मेरा ऑर्डर'. Not hand-checked yet.

Label note: docs/product-scope.md sends other languages to needs a look. The prompt does not say so yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | needs_a_look | inbox (Routine) |

Notes: topic 'Orders and delivery', urgency normal, anger 2, flags none, sure True. Word check: none.
Summary: Customer ordered a bag last week (order TF-21455) and has had no delivery update. She asks when it will arrive. This is a routine where-is-my-order question with no travel date or stated deadline, so it can wait for the inbox session.
- Order placed and order number, identifying the order: "मैंने पिछले हफ्ते एक बैग ऑर्डर किया था, ऑर्डर नंबर TF-21455."
- No update received, mild frustration: "अभी तक कोई अपडेट नहीं आया है।"
- Asks for delivery timing, normal question: "कृपया बताइए कब तक पहुंचेगा।"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/out-of-office · auto_reply

Failed 3 of 3 runs. Subject: 'Automatic reply: Your Tripfold order has shipped'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | closed | needs_a_look (The AI is unsure) |
| topic | Spam or not for me | Orders and delivery |
| summary | about the email, not the rules | Out-of-office auto reply from a partner contact (Brightline Partners) to an email about a Tripfold order that has shipped. It needs no action from the business. It is not a bulk or corporate order request as far as the email shows, so the corporate rule does not match. Filed under Orders and delivery because it concerns an order, but the sender is out of office until 10 November, so sure is false. |

Notes: topic 'Orders and delivery', urgency low, anger 1, flags none, sure False. Word check: none.
Summary: Out-of-office auto reply from a partner contact (Brightline Partners) to an email about a Tripfold order that has shipped. It needs no action from the business. It is not a bulk or corporate order request as far as the email shows, so the corporate rule does not match. Filed under Orders and delivery because it concerns an order, but the sender is out of office until 10 November, so sure is false.
- Subject refers to a Tripfold order that has shipped: "Automatic reply: Your Tripfold order has shipped"
- Sender is out of office, so no reply is expected before Monday: "I am out of office until Monday, 10 November, with limited access to email."

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/praise-ladakh · routine

Failed 2 of 3 runs. Subject: 'Took the backpack to Ladakh'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | needs_a_look (The AI is unsure) |
| summary | about the email, not the rules | Customer praise: the Trail backpack held up through two weeks in Ladakh, and they plan to recommend it. This is general product feedback rather than a question, so no listed topic fits well. Not spam, since it is about the business's product. No rule matches: not travelling soon with a missing order, not damaged, not corporate, not a courier or marketplace newsletter. |

Notes: topic 'Product questions', urgency low, anger 1, flags none, sure False. Word check: none.
Summary: Customer praise: the Trail backpack held up through two weeks in Ladakh, and they plan to recommend it. This is general product feedback rather than a question, so no listed topic fits well. Not spam, since it is about the business's product. No rule matches: not travelling soon with a missing order, not damaged, not corporate, not a courier or marketplace newsletter.
- praise about product durability: "Just wanted to say the Trail backpack survived two weeks in Ladakh, dust storms and all."
- positive recommendation: "Great job, will recommend to friends!"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/third-follow-up · repeat_contact, history

Failed 3 of 3 runs. Subject: 'Following up again - order TF-19302'. Not hand-checked yet.

Label note: docs/product-scope.md alerts on 'a third email about the same thing'. decide does not count repeats yet, so this fails until it does.

| Check | Expected | Got |
| --- | --- | --- |
| route | alert | inbox (Routine) |

Notes: topic 'Orders and delivery', urgency high, anger 2, flags none, sure True. Word check: none.
Summary: Repeat follow-up on order TF-19302. The parcel has been stuck since leaving the Delhi hub for 9 days with no tracking movement, so the customer has no delivery and no workaround. This is a late delivery matter, and the sender has now written three times.
- Repeat contact and delay: "following up again on order TF-19302"
- Stuck tracking, 9 days: "It's now 9 days and the tracking hasn't moved since it left the Delhi hub."
- Mild frustration, asks for action: "Could someone please look into it?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/unauthorised-reseller · word_false_positive

Failed 1 of 3 runs. Subject: 'Is this seller genuine?'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | needs_a_look (The AI is unsure) |

Notes: topic 'Product questions', urgency normal, anger 1, flags none, sure False. Word check: none.
Summary: Pre-purchase question from a prospective buyer. He found a Tripfold Voyager for Rs 3,000 less on a third-party site, TravelKart, and asks whether it is an unauthorised reseller and whether the 2-year warranty still applies if he buys there. The facts do not cover reseller authorisation or warranty for third-party sellers, so the owner must decide the answer.
- Asks whether the seller is an unauthorised reseller: "Are they an unauthorised reseller?"
- Asks whether the 2-year warranty applies to a purchase from that seller: "Would the 2-year warranty still apply if I buy from them?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no
