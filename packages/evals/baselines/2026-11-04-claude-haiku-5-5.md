# Herald score report

Model `claude-haiku-5-5` (anthropic), temperature API default (1.0), 3 run(s) per case, prompt `d0153d058124`, commit `857b786`, 2026-11-03 19:15 UTC.

> **68 of 68 cases are not hand-checked yet.** They were drafted with an AI's help. Read each one and set `reviewed = true` when you agree with its label; until then these numbers are a draft.

## Headline

| Measure | ledgerly | tripfold | All | Target |
| --- | --- | --- | --- | --- |
| Missed alerts | 0% (0/21) ✓ | 6% (3/51) ✗ | 4% (3/72) ✓ | ≤ 5% |
| False alarms | 12% (3/24) ✓ | 24% (15/63) ✓ | 21% (18/87) ✓ | ≤ 30% |
| Topic accuracy | 100% (45/45) ✓ | 97% (90/93) ✓ | 98% (135/138) ✓ | ≥ 85% |
| Needs a look | 0% (0/57) ✓ | 7% (11/147) ✓ | 5% (11/204) ✓ | < 10% |
| Rule verdicts right | 100% (27/27) ✓ | 100% (54/54) ✓ | 100% (81/81) ✓ | ≥ 90% |
| Route right | 95% (54/57) | 82% (120/147) | 85% (174/204) |  |
| Every label right | 95% (54/57) | 82% (120/147) | 85% (174/204) |  |
| Urgency right | 100% (3/3) | 90% (19/21) | 92% (22/24) |  |
| Anger in range | 100% (12/12) | 100% (30/30) | 100% (42/42) |  |
| Quotes taken from the email | 100% (120/120) | 100% (339/339) | 100% (459/459) |  |
| Summaries free of rule talk | 61% (35/57) | 65% (95/147) | 64% (130/204) |  |
| Model errors (left out above) | 0 of 57 | 0 of 147 | 0 of 204 | 0 |
| Time per email, median / p95 | 5670 / 9014 ms | 5869 / 7927 ms | 5830 / 8250 ms | |

## Safety floor

Floor flags the labels expect, and who caught them. The word check runs beside the AI; either one alerts.

| Caught by | Share |
| --- | --- |
| AI | 100% (36/36) |
| Word check | 33% (12/36) |
| Either (what the owner gets) | 100% (36/36) |

Word check raised a floor flag the label does not expect (21 runs). No rule can undo these alerts:
- ledgerly/court-reporters-gst-field: legal_threat ×3
- tripfold/bag-is-the-bomb: safety ×3
- tripfold/food-court-popup: legal_threat ×3
- tripfold/hacked-zip-open: account_or_data ×3
- tripfold/newsletter-mentions-fraud: account_or_data ×3
- tripfold/sue-is-a-name: legal_threat ×3
- tripfold/unauthorised-reseller: account_or_data ×3

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
| routine | 93% (39/42) |
| rule | 92% (36/39) |
| rule_conflict | 100% (3/3) |
| rule_near_miss | 100% (12/12) |
| safety_floor | 100% (36/36) |
| sarcasm | 100% (6/6) |
| spam | 100% (12/12) |
| thread | 100% (6/6) |
| trick | 100% (9/9) |
| unclear | 100% (3/3) |
| word_false_positive | 14% (3/21) |
| word_miss | 100% (24/24) |

## Routes

Rows are the label, columns what Herald did. `either` is a case where more than one route is fine.

| Label \ Got | alert | needs_a_look | inbox | closed |
| --- | --- | --- | --- | --- |
| alert | 69 | 0 | 3 | 0 |
| needs_a_look | 0 | 0 | 3 | 0 |
| inbox | 18 | 3 | 66 | 0 |
| closed | 0 | 2 | 1 | 21 |
| either | 3 | 6 | 9 | 0 |

## Cases whose route changed between runs (1)

- tripfold/out-of-office: inbox ×1, needs_a_look ×2

## Failing cases (10)

### ledgerly/court-reporters-gst-field · word_false_positive

Failed 3 of 3 runs. Subject: 'Extra field on invoices'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | alert (Safety floor: legal_threat) |
| no_flag:legal_threat | not raised | raised by word check |

Notes: topic 'Feature requests', urgency low, anger 1, flags none, sure True. Word check: legal_threat.
Summary: A court reporting agency using Ledgerly asks for a new 'case number' field on its invoice template. This is a feature idea, not a broken invoice.
- Feature request: asks to add a new field to the invoice template: "Could we add a 'case number' field to our"

Rule verdicts: invoices-broken no; payout-late no; feature-idea yes "Could we add a 'case number' field to our invoice template?"; vendor-marketing no

### tripfold/bag-is-the-bomb · word_false_positive

Failed 3 of 3 runs. Subject: 'Love it'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | alert (Safety floor: safety) |
| no_flag:safety | not raised | raised by word check |

Notes: topic 'Product questions', urgency low, anger 1, flags none, sure True. Word check: safety.
Summary: Customer praises a duffel bag and asks whether it comes in olive, a product question about colour before buying.
- praise: "Honestly this duffel is the bomb. Fits everything for a week."
- product question about colour: "Do you make it in olive?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/food-court-popup · word_false_positive

Failed 3 of 3 runs. Subject: 'Laptop sleeve?'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | alert (Safety floor: legal_threat) |
| no_flag:legal_threat | not raised | raised by word check |
| summary | about the email, not the rules | Pre-purchase product question from a customer who saw the pop-up stall at Phoenix Mall. They ask whether the Commuter backpack has a padded sleeve for a 16-inch laptop. No order, delivery, or travel issue is mentioned, so no rule applies. |

Notes: topic 'Product questions', urgency normal, anger 1, flags none, sure True. Word check: legal_threat.
Summary: Pre-purchase product question from a customer who saw the pop-up stall at Phoenix Mall. They ask whether the Commuter backpack has a padded sleeve for a 16-inch laptop. No order, delivery, or travel issue is mentioned, so no rule applies.
- Product question about the backpack's laptop sleeve: "Does the Commuter backpack have a padded sleeve for a 16-inch laptop?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/hacked-zip-open · word_false_positive, rule

Failed 3 of 3 runs. Subject: 'Zip jammed'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | alert (Safety floor: account_or_data) |
| no_flag:account_or_data | not raised | raised by word check |
| summary | about the email, not the rules | Customer's duffel zip jammed shut on a train, bag is about six weeks old, and they ask whether the zip can be replaced under the 2-year warranty. Rule damaged: yes, the zip broke during use. Rule travel-soon: no, no trip in the next 48 hours is mentioned. Rule corporate: no. Rule newsletters: no. |

Notes: topic 'Warranty claims', urgency normal, anger 1, flags none, sure True. Word check: account_or_data.
Summary: Customer's duffel zip jammed shut on a train, bag is about six weeks old, and they ask whether the zip can be replaced under the 2-year warranty. Rule damaged: yes, the zip broke during use. Rule travel-soon: no, no trip in the next 48 hours is mentioned. Rule corporate: no. Rule newsletters: no.
- Warranty claim: broke after 30 days, within the 2-year warranty: "Bag is a month and a half old."
- Customer asks for a warranty replacement of the zip: "Can the zip be replaced under warranty?"
- Rule damaged: yes, bag broke during use: "The zip on my duffel jammed shut on the train"
- Customer forced the bag open, so the zip may be damaged further; worth noting: "I hacked it open with a pen knife to get my things out."

Rule verdicts: travel-soon no; damaged yes "The zip on my duffel jammed shut on the train and I hacked it open with a pen knife to get"; corporate no; newsletters no

### tripfold/hindi-order-status · other_language

Failed 3 of 3 runs. Subject: 'मेरा ऑर्डर'. Not hand-checked yet.

Label note: docs/product-scope.md sends other languages to needs a look. The prompt does not say so yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | needs_a_look | inbox (Routine) |

Notes: topic 'Orders and delivery', urgency normal, anger 1, flags none, sure True. Word check: none.
Summary: Customer placed a bag order last week (order TF-21455) and has had no update. They ask when it will arrive. This is a calm delivery-status question that can wait for today's inbox session.
- No update on order status: "अभी तक कोई अपडेट नहीं आया है।"
- Asks for delivery date, calm tone: "कृपया बताइए कब तक पहुंचेगा।"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/out-of-office · auto_reply

Failed 3 of 3 runs. Subject: 'Automatic reply: Your Tripfold order has shipped'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | closed | inbox (Routine) |
| topic | Spam or not for me | Orders and delivery |

Notes: topic 'Orders and delivery', urgency low, anger 1, flags none, sure True. Word check: none.
Summary: Out-of-office auto-reply from a business contact, sent in response to the Tripfold order shipping notice. It says the sender is away until Monday, 10 November, and gives a colleague's address for urgent matters. It contains no request, complaint or cancellation, so no action is needed beyond noting the absence.
- Shows this is an auto-reply to the order shipping notice: "Subject: Automatic reply: Your Tripfold order has shipped"
- Out-of-office notice with no request: "I am out of office until Monday, 10 November, with limited access to email."

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/praise-ladakh · routine

Failed 3 of 3 runs. Subject: 'Took the backpack to Ladakh'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | needs_a_look (The AI is unsure) |
| summary | about the email, not the rules | Customer praise about the Trail backpack, which survived two weeks in Ladakh. No problem, question or order issue. Rules: travel-soon no, damaged no, corporate no, newsletters no. Filed under Product questions as the closest product topic, but no listed topic fits praise, so the owner should confirm. |

Notes: topic 'Product questions', urgency low, anger 1, flags none, sure False. Word check: none.
Summary: Customer praise about the Trail backpack, which survived two weeks in Ladakh. No problem, question or order issue. Rules: travel-soon no, damaged no, corporate no, newsletters no. Filed under Product questions as the closest product topic, but no listed topic fits praise, so the owner should confirm.
- Praise for the product, low urgency, anger 1: "Just wanted to say the Trail backpack survived two weeks in Ladakh, dust storms and all."
- Recommendation, no cancel or legal risk: "Great job, will recommend to friends!"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/sue-is-a-name · word_false_positive

Failed 3 of 3 runs. Subject: 'Exchange for a different colour'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | alert (Safety floor: legal_threat) |
| no_flag:legal_threat | not raised | raised by word check |

Notes: topic 'Returns and exchanges', urgency normal, anger 1, flags none, sure True. Word check: legal_threat.
Summary: Customer asks to exchange an unused Aero cabin bag in teal for navy. This is a real exchange question that can wait for today's inbox session.
- exchange request for different colour: "I received the Aero cabin in teal but would prefer navy."
- unused, so eligible under return/exchange rules: "It's unused. Can I exchange it?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/third-follow-up · repeat_contact, history

Failed 3 of 3 runs. Subject: 'Following up again - order TF-19302'. Not hand-checked yet.

Label note: docs/product-scope.md alerts on 'a third email about the same thing'. decide does not count repeats yet, so this fails until it does.

| Check | Expected | Got |
| --- | --- | --- |
| route | alert | inbox (Routine) |

Notes: topic 'Orders and delivery', urgency high, anger 2, flags none, sure True. Word check: none.
Summary: Customer is following up for the second time on order TF-19302. Tracking has not moved since the Delhi hub for 9 days, so the order looks stuck in transit and needs someone to investigate.
- Repeat follow-up, order stuck for 9 days: "Hi, following up again on order TF-19302. It's now 9 days and the tracking hasn't moved"
- Customer asks for someone to act: "Could someone please look into it?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/unauthorised-reseller · word_false_positive

Failed 3 of 3 runs. Subject: 'Is this seller genuine?'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | alert (Safety floor: account_or_data) |
| no_flag:account_or_data | not raised | raised by word check |

Notes: topic 'Product questions', urgency normal, anger 1, flags none, sure True. Word check: account_or_data.
Summary: Pre-purchase question: the customer found the Voyager cheaper on a third-party site, TravelKart, and asks whether it is an unauthorised reseller and whether the 2-year warranty applies to purchases from that seller. No trip, damage, or cancellation is mentioned.
- Pre-purchase question about the seller's authorisation: "Are they an unauthorised reseller?"
- Question about warranty coverage on a third-party purchase: "Would the 2-year warranty still apply if I buy from them?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

## Changes since the compared run

Compared with 2026-11-03 19:03 UTC, model claude-haiku-5-5, prompt d0153d058124.

Now right more often (3):
- tripfold/airport-handle-snapped (0/3 → 3/3 runs right)
- tripfold/flight-tomorrow-bag-arrived (2/3 → 3/3 runs right)
- tripfold/warranty-zip-eight-months (2/3 → 3/3 runs right)

Now wrong more often (1):
- tripfold/praise-ladakh (1/3 → 0/3 runs right)
