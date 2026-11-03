# Herald score report

Model `claude-haiku-5-5` (anthropic), temperature API default (1.0), 3 run(s) per case, prompt `d0153d058124`, commit `b02493b`, 2026-11-03 19:03 UTC.

> **68 of 68 cases are not hand-checked yet.** They were drafted with an AI's help. Read each one and set `reviewed = true` when you agree with its label; until then these numbers are a draft.

## Headline

| Measure | ledgerly | tripfold | All | Target |
| --- | --- | --- | --- | --- |
| Missed alerts | 0% (0/21) ✓ | 12% (6/51) ✗ | 8% (6/72) ✗ | ≤ 5% |
| False alarms | 12% (3/24) ✓ | 25% (15/60) ✓ | 21% (18/84) ✓ | ≤ 30% |
| Topic accuracy | 100% (45/45) ✓ | 97% (90/93) ✓ | 98% (135/138) ✓ | ≥ 85% |
| Needs a look | 0% (0/57) ✓ | 7% (10/147) ✓ | 5% (10/204) ✓ | < 10% |
| Rule verdicts right | 100% (27/27) ✓ | 98% (53/54) ✓ | 99% (80/81) ✓ | ≥ 90% |
| Route right | 95% (54/57) | 80% (117/147) | 84% (171/204) |  |
| Every label right | 95% (54/57) | 79% (116/147) | 83% (170/204) |  |
| Urgency right | 100% (3/3) | 90% (19/21) | 92% (22/24) |  |
| Anger in range | 100% (12/12) | 100% (30/30) | 100% (42/42) |  |
| Quotes taken from the email | 100% (114/114) | 100% (336/336) | 100% (450/450) |  |
| Summaries free of rule talk | 58% (33/57) | 69% (102/147) | 66% (135/204) |  |
| Model errors (left out above) | 0 of 57 | 0 of 147 | 0 of 204 | 0 |
| Time per email, median / p95 | 5863 / 8340 ms | 5954 / 7933 ms | 5907 / 8085 ms | |

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
| tripfold/damaged | 94% (17/18) | 0 | 1 |
| tripfold/travel-soon | 100% (24/24) | 0 | 0 |

## Slices

| Tag | Every label right |
| --- | --- |
| about_to_cancel | 100% (6/6) |
| angry_routine | 100% (6/6) |
| auto_reply | 0% (0/3) |
| calm_urgent | 80% (12/15) |
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
| rule | 82% (32/39) |
| rule_conflict | 0% (0/3) |
| rule_near_miss | 92% (11/12) |
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
| alert | 66 | 0 | 6 | 0 |
| needs_a_look | 0 | 0 | 3 | 0 |
| inbox | 18 | 3 | 66 | 0 |
| closed | 0 | 1 | 2 | 21 |
| either | 3 | 6 | 9 | 0 |

## Cases whose route changed between runs (3)

- tripfold/flight-tomorrow-bag-arrived: inbox ×2, needs_a_look ×1
- tripfold/out-of-office: inbox ×2, needs_a_look ×1
- tripfold/praise-ladakh: inbox ×1, needs_a_look ×2

## Failing cases (13)

### ledgerly/court-reporters-gst-field · word_false_positive

Failed 3 of 3 runs. Subject: 'Extra field on invoices'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | alert (Safety floor: legal_threat) |
| no_flag:legal_threat | not raised | raised by word check |
| summary | about the email, not the rules | A court reporting agency that uses Ledgerly asks for a new 'case number' field on its invoice template. This is an idea for a new feature, not a broken invoice or payout. Rule feature-idea matches. Rules invoices-broken, payout-late and vendor-marketing do not match. |

Notes: topic 'Feature requests', urgency low, anger 1, flags none, sure True. Word check: legal_threat.
Summary: A court reporting agency that uses Ledgerly asks for a new 'case number' field on its invoice template. This is an idea for a new feature, not a broken invoice or payout. Rule feature-idea matches. Rules invoices-broken, payout-late and vendor-marketing do not match.
- Rule feature-idea matches: the email only asks for a new field: "Could we add a 'case number' field to our invoice template?"

Rule verdicts: invoices-broken no; payout-late no; feature-idea yes "Could we add a 'case number' field to our invoice template?"; vendor-marketing no

### tripfold/airport-handle-snapped · calm_urgent, rule, rule_conflict

Failed 3 of 3 runs. Subject: 'Handle broke at the airport'. Not hand-checked yet.

Label note: The profile names this exact bad day. The `damaged` rule sets urgency to high, which can override the AI's urgent and stop the alert: the label is alert because the owner would want to know.

| Check | Expected | Got |
| --- | --- | --- |
| route | alert | inbox (Routine) |

Notes: topic 'Damaged or defective', urgency urgent, anger 3, flags none, sure True. Word check: none.
Summary: Customer's Tripfold Voyager telescopic handle snapped off at check-in at Bengaluru airport; they have a connecting flight in Delhi and board in two hours, so they cannot move the bag. The bag arrived last month, so it falls under the 30-day damaged window, and the handle is covered by the 2-year warranty. Harm is happening now with a travel deadline.
- Broken bag at airport, travel deadline now: "the telescopic handle on my Tripfold Voyager just snapped off at check-in."
- Cannot continue travel with the bag: "I have a connecting flight in Delhi and can't drag a 23 kg bag through the terminal like this."
- Recent delivery, within 30 days: "The bag arrived last month."
- Time pressure: "I board in two hours."

Rule verdicts: travel-soon no; damaged yes "the telescopic handle on my Tripfold Voyager just snapped off at check-in"; corporate no; newsletters no

### tripfold/bag-is-the-bomb · word_false_positive

Failed 3 of 3 runs. Subject: 'Love it'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | alert (Safety floor: safety) |
| urgency | low | normal |
| no_flag:safety | not raised | raised by word check |

Notes: topic 'Product questions', urgency normal, anger 1, flags none, sure True. Word check: safety.
Summary: Customer praises the duffel and asks whether it comes in olive. This is a product question about colour options, which can wait for today's inbox session.
- praise, low urgency: "Honestly this duffel is the bomb."
- product question about colour: "Do you make it in olive?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/flight-tomorrow-bag-arrived · rule_near_miss

Failed 1 of 3 runs. Subject: "Cabin size check before tomorrow's flight". Not hand-checked yet.

Label note: Travelling tomorrow, but the order has arrived, so the travel rule does not match.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | needs_a_look (The AI is unsure) |

Notes: topic 'Product questions', urgency normal, anger 1, flags none, sure False. Word check: none.
Summary: Customer asks whether the Aero cabin bag fits IndiGo's 55 x 35 x 25 cm and 7 kg cabin limit with the expander closed, before a flight tomorrow. The bag has already arrived, so this is a sizing question about a product, not a delivery problem. It is a real question that can wait for today's inbox session, though the flight is tomorrow.
- sizing question before flight: "Will the bag fit when the expander is closed?"
- flight is tomorrow: "I'm flying IndiGo tomorrow."

Rule verdicts: travel-soon no "My Aero cabin bag arrived yesterday, thank you!"; damaged no; corporate no; newsletters no

### tripfold/food-court-popup · word_false_positive

Failed 3 of 3 runs. Subject: 'Laptop sleeve?'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | alert (Safety floor: legal_threat) |
| no_flag:legal_threat | not raised | raised by word check |
| summary | about the email, not the rules | Pre-purchase product question asking whether the Commuter backpack has a padded sleeve that fits a 16-inch laptop. Calm, no order or delivery issue, and no rule applies. |

Notes: topic 'Product questions', urgency normal, anger 1, flags none, sure True. Word check: legal_threat.
Summary: Pre-purchase product question asking whether the Commuter backpack has a padded sleeve that fits a 16-inch laptop. Calm, no order or delivery issue, and no rule applies.
- Product question about laptop sleeve in the Commuter backpack: "Does the Commuter backpack have a padded sleeve for a 16-inch laptop?"
- Calm, pre-purchase context, no order problem: "I saw your pop-up stall near the food court at Phoenix Mall last weekend."

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/hacked-zip-open · word_false_positive, rule

Failed 3 of 3 runs. Subject: 'Zip jammed'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | alert (Safety floor: account_or_data) |
| no_flag:account_or_data | not raised | raised by word check |

Notes: topic 'Warranty claims', urgency normal, anger 1, flags none, sure True. Word check: account_or_data.
Summary: Customer's duffel zip jammed shut on a train and they forced it open with a pen knife. The bag is about six weeks old, so it is past the 30-day damage window but within the 2-year wheel, zip and handle warranty. They ask whether the zip can be replaced under warranty. This is a calm warranty question that can wait for today's inbox session.
- Zip failure during use: "The zip on my duffel jammed shut on the train"
- Age of bag, past 30 days: "Bag is a month and a half old."
- Warranty question: "Can the zip be replaced under warranty?"

Rule verdicts: travel-soon no; damaged yes "The zip on my duffel jammed shut on the train and I hacked it open with a pen knife to get"; corporate no; newsletters no

### tripfold/hindi-order-status · other_language

Failed 3 of 3 runs. Subject: 'मेरा ऑर्डर'. Not hand-checked yet.

Label note: docs/product-scope.md sends other languages to needs a look. The prompt does not say so yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | needs_a_look | inbox (Routine) |

Notes: topic 'Orders and delivery', urgency normal, anger 1, flags none, sure True. Word check: none.
Summary: Customer ordered a bag last week (order TF-21455) and has had no update yet. They are asking when it will arrive. This is a routine delivery status question with no travel deadline mentioned.
- No update since ordering, which is the reason for contact: "अभी तक कोई अपडेट नहीं आया है।"
- Asks for the delivery date, a real question that can wait: "कृपया बताइए कब तक पहुंचेगा।"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/out-of-office · auto_reply

Failed 3 of 3 runs. Subject: 'Automatic reply: Your Tripfold order has shipped'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | closed | inbox (Routine) |
| topic | Spam or not for me | Orders and delivery |

Notes: topic 'Orders and delivery', urgency low, anger 1, flags none, sure True. Word check: none.
Summary: Out-of-office auto reply to a Tripfold shipping notice. The sender is away until Monday 10 November with limited email access. It asks for no action and raises no complaint, so it is a low-priority note on an existing order.
- Auto reply to the shipping notice for a Tripfold order: "Subject: Automatic reply: Your Tripfold order has shipped"
- Sender is away with limited email access, so no reply is expected now: "I am out of office until Monday, 10 November, with limited access to email."

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/praise-ladakh · routine

Failed 2 of 3 runs. Subject: 'Took the backpack to Ladakh'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | needs_a_look (The AI is unsure) |
| summary | about the email, not the rules | Customer praises the Trail backpack after two weeks in Ladakh and says they will recommend it to friends. This is product feedback with no problem or request. No listed topic fits praise exactly, so I filed it under the closest product topic. None of the rules match. |

Notes: topic 'Product questions', urgency low, anger 1, flags none, sure False. Word check: none.
Summary: Customer praises the Trail backpack after two weeks in Ladakh and says they will recommend it to friends. This is product feedback with no problem or request. No listed topic fits praise exactly, so I filed it under the closest product topic. None of the rules match.
- praise, low urgency and calm anger: "Just wanted to say the Trail backpack survived two weeks in Ladakh, dust storms and all."
- positive recommendation, not a cancellation: "Great job, will recommend to friends!"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/sue-is-a-name · word_false_positive

Failed 3 of 3 runs. Subject: 'Exchange for a different colour'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | alert (Safety floor: legal_threat) |
| no_flag:legal_threat | not raised | raised by word check |

Notes: topic 'Returns and exchanges', urgency normal, anger 1, flags none, sure True. Word check: legal_threat.
Summary: Customer asks to exchange an unused Aero cabin bag in teal for navy. This is a routine exchange request that can wait for today's inbox session.
- exchange request for a different colour: "I received the Aero cabin in teal but would prefer navy. It's unused. Can I exchange it?"

Rule verdicts: travel-soon no; damaged no "It's unused. Can I exchange it?"; corporate no; newsletters no

### tripfold/third-follow-up · repeat_contact, history

Failed 3 of 3 runs. Subject: 'Following up again - order TF-19302'. Not hand-checked yet.

Label note: docs/product-scope.md alerts on 'a third email about the same thing'. decide does not count repeats yet, so this fails until it does.

| Check | Expected | Got |
| --- | --- | --- |
| route | alert | inbox (Routine) |
| summary | about the email, not the rules | Repeat follow-up on order TF-19302. The parcel is 9 days old and tracking has not moved since leaving the Delhi hub, which is well past the 5-7 day window for other cities. No rule matches: the customer is not travelling within 48 hours, the bag is not damaged, it is not corporate, and it is not a newsletter. |

Notes: topic 'Orders and delivery', urgency high, anger 2, flags none, sure True. Word check: none.
Summary: Repeat follow-up on order TF-19302. The parcel is 9 days old and tracking has not moved since leaving the Delhi hub, which is well past the 5-7 day window for other cities. No rule matches: the customer is not travelling within 48 hours, the bag is not damaged, it is not corporate, and it is not a newsletter.
- Repeat follow-up and delay: "Hi, following up again on order TF-19302."
- Stuck tracking, 9 days: "It's now 9 days and the tracking hasn't moved since it left the Delhi hub."
- Asks for action: "Could someone please look into it?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/unauthorised-reseller · word_false_positive

Failed 3 of 3 runs. Subject: 'Is this seller genuine?'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| route | inbox | alert (Safety floor: account_or_data) |
| no_flag:account_or_data | not raised | raised by word check |
| summary | about the email, not the rules | Pre-purchase question from a prospective buyer about whether the Voyager is sold by an unauthorised reseller (TravelKart) and whether the 2-year warranty applies if bought there. Not about an existing order, so no rules match. |

Notes: topic 'Product questions', urgency normal, anger 1, flags none, sure False. Word check: account_or_data.
Summary: Pre-purchase question from a prospective buyer about whether the Voyager is sold by an unauthorised reseller (TravelKart) and whether the 2-year warranty applies if bought there. Not about an existing order, so no rules match.
- Pre-purchase question about the reseller's authorisation: "Are they an unauthorised reseller?"
- Asks whether the warranty applies when buying from this seller: "Would the 2-year warranty still apply if I buy from them?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no

### tripfold/warranty-zip-eight-months · routine, rule

Failed 1 of 3 runs. Subject: 'Zip broken'. Not hand-checked yet.

| Check | Expected | Got |
| --- | --- | --- |
| rule:damaged | yes | no |
| summary | about the email, not the rules | Customer's check-in bag main zip broke during use on their last trip, 8 months after purchase. They ask whether the warranty covers it. This is a warranty claim within the 2-year zip warranty. It is a real question that can wait for the inbox session. The damaged rule matches because the bag broke during use. |

Notes: topic 'Warranty claims', urgency normal, anger 1, flags none, sure True. Word check: none.
Summary: Customer's check-in bag main zip broke during use on their last trip, 8 months after purchase. They ask whether the warranty covers it. This is a warranty claim within the 2-year zip warranty. It is a real question that can wait for the inbox session. The damaged rule matches because the bag broke during use.
- Broke during use, matching the damaged rule: "The main zip on my check-in bag broke on my last trip."
- Warranty question, zip is within the 2-year coverage: "Is this covered by the warranty?"

Rule verdicts: travel-soon no; damaged no; corporate no; newsletters no
