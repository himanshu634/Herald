# Herald: Product Scope

> Snapshot of the [original scope doc](https://claude.ai/artifact/GDyVnqcyeFuU2FBDHQmeZK), taken 2026-11-03. Where later decisions differ, [decisions.md](decisions.md) wins.

Clarity.tech take-home · 2026-11-03 · Eddie

## Context

Build Herald, an email triage product for a business run by one person: an AI pipeline built on LangGraph reads every customer email, and anything critical or from a very angry customer alerts the owner straight away. It must work for any business, so the owner describes their business and writes their own rules instead of the product hard-coding them.

The brief, as given and clarified:

- The company receives a high volume of customer emails.
- A dashboard with a LangGraph pipeline that classifies emails by status.
- Critical tickets, and customers who are extremely angry with the brand, escalate to a human.
- One person manages everything: they answer emails, receive the alerts and set the rules.
- The platform is business agnostic: the owner adds the rules the AI follows.

**How "status" is read.** The word is ambiguous, so it is split in two. *Notes* are what the AI says about an email: topic, urgency, anger. *Status* is where the email stands: in the inbox, needs you now, in progress, done. The AI only writes notes; the owner's rules and the owner's own actions move the status. The write-up states this reading as a deliberate choice.

| Assumption | Default until told otherwise | What it changes |
| --- | --- | --- |
| Time budget | About 5 working days | Where the cut line sits in the feature list |
| Data | Sample emails for three example businesses, plus a "send test email" box | No real inbox connection in the build |
| Language | English first; other languages flagged for the owner | Scope of the test emails |
| Users | One owner per workspace; each business gets its own workspace | No teams, roles or permissions |
| Required tech | LangGraph (given); everything else is my choice | Decided in the technical phase |
| Reviewers | Engineers and product people who run it or watch a demo | The write-up and demo matter as much as the code |

## The owner

The user is a solo owner who wears every hat, so the product's real job is protecting their attention: interrupt them only for what cannot wait, and make everything else quick to clear. For a team, escalation means handing a ticket to the right person; for one person, it means deciding whether to buzz their phone.

Think of an online bakery, a freelance web developer with retainer clients, or a small software app run by its founder. Same problem, very different ideas of what counts as urgent.

| Hat the owner wears | What they need | Where it lives in the product |
| --- | --- | --- |
| Setting up | Describe the business, pick topics and write rules in plain words, in one sitting | Setup and rules |
| Being on call | An alert only when something is urgent, with enough in it to act from the phone | Alert |
| Working the inbox | A list already sorted, with the reason behind each note | Inbox, email detail |
| Checking the AI | Confidence that nothing urgent slipped through, and a one-click way to fix mistakes | Summary, corrections |

Jobs to be done:

1. When something urgent arrives, tell me now, even if I am not looking at the dashboard.
2. When I sit down to work, show me the most important emails first, already sorted.
3. When my business has its own idea of urgent, let me say so in plain words.
4. When the AI gets it wrong, let me fix it in one click so it learns my business.

## The fences

The product sorts, flags and alerts; it never replies to customers on its own and never makes money decisions. Anything outside the Build column is faked for the demo or left out on purpose.

| Area | Build | Fake for the demo, or leave out |
| --- | --- | --- |
| Email intake | Sample inboxes and a "send test email" box | A real Gmail or Outlook connection |
| Business setup | Business description, topic list, important contacts, starter templates for a few business types | Importing settings from other tools |
| Rules | Plain-language rules, a built-in safety floor, a test before any rule goes live | Complex rule logic with nested conditions |
| AI notes | Topic, urgency, anger, risk flags, a one-line summary and the quoted lines behind each note | Training a custom model |
| Alerts | Phone or email alert for urgent emails; one reminder if it is not opened | Phone calls, on-call rotations |
| Inbox | Sorted list, email detail, "on it" or "not urgent", corrections | Assigning to others, team views |
| Replies | Nothing sent to customers | Auto-replies; drafts are a stretch goal and always sent by the owner |
| Quality | Test emails with known answers and a score report | Live experiments |
| Accounts | One owner per workspace | Teams, roles, billing |

Non-goals, even in a later version:

- **No replying on the owner's behalf.** The AI may draft; the owner sends.
- **No money or account decisions.** Refunds, credits and cancellations stay with the owner.
- **No rule can silence a safety, security or legal warning.**
- **No helpdesk replacement.** A business that outgrows one person moves to a tool like Zendesk; this product is for before that.

## Make it fit any business

The platform knows nothing about a business until the owner tells it, through four things set up once and changed any time. Each one is plain words or a short list; none needs a developer.

| Setup piece | What the owner gives | How the AI uses it | Example: online bakery |
| --- | --- | --- | --- |
| Business profile | A few sentences: what you sell, who your customers are, what a bad day looks like | Background for every email it reads | "We bake custom cakes to order; a missed delivery on the event day is a disaster" |
| Topics | A short list of what customers write about | Files each email under one topic | Orders, Delivery, Custom designs, Allergies, Payments |
| Important contacts | Names, email addresses or company domains that always matter | Raises urgency; makes moderate anger worth an alert | Wedding planners the bakery works with |
| Rules | "When ... then ..." sentences | Checked on every email; the result decides what happens | "When an order is for today or tomorrow and something is wrong, alert me" |

Each business type gets a starter template (topics, a few rules and sample emails), so setup starts from a sensible draft rather than a blank page. The build ships three: an online shop, an appointments business such as a salon, and a software subscription.

| A rule can | Example |
| --- | --- |
| Alert me now | When a customer mentions a reaction to an ingredient, alert me |
| Raise or lower urgency | When the email is about a wholesale order, treat it as high |
| Set the topic | When the email mentions an invoice or receipt, file it under Payments |
| Mark someone as important | When the sender is from bigclient.com, treat them as important |
| Close quietly | When it is a supplier newsletter, close it |

Rules come in two kinds, and each rule card says which:

- **Exact checks** look at facts: who sent it, which words appear, the topic, whether the sender is important. They behave the same way every time.
- **Judgement checks** are a plain-language question the AI answers, such as "the customer sounds like they might cancel". The AI answers yes or no and quotes the line that decided it.

**Test before it goes live.** When the owner writes or edits a rule, the product runs it on past or sample emails and shows what would have changed, with the emails themselves. The owner saves only after seeing that, so a rule that would buzz them twenty times a day is caught before it does.

**The safety floor.** A short list of built-in alerts sits beneath every rule and cannot be switched off: threats of violence or self-harm, a possible hacked account or data leak, and legal threats. Owner rules can add urgency but never push an email below this floor. Separately, an email the AI cannot read lands in "Needs a look" instead of disappearing.

When rules disagree, the order is: safety floor first, then the owner's rules (the most urgent result wins), then the built-in defaults.

## What the AI notes on every email

The AI writes the same few notes on every email whatever the business; only the topic list and the rules change. Urgency and anger are noted separately, so a calm email about a disaster and a furious email about something small are never confused.

| Note | Values | Where it comes from |
| --- | --- | --- |
| Topic | The owner's own list, plus "Spam or not for me" | AI, using the owner's topics |
| Urgency | Urgent, High, Normal, Low | AI, raised or lowered by the owner's rules |
| Anger | 1 (calm) to 5 (extremely angry) | AI, using a written scale |
| Risk flags | Safety, hacked account or data, legal threat, going public, about to cancel, abusive | AI, plus a simple word check |
| Repeat contact | How many times this customer wrote about the same thing | The product, from past emails |
| Important contact | Yes or no | The owner's list |
| Summary and proof | One line, plus the exact lines from the email behind each note | AI |
| Sure or unsure | Whether the AI is confident in its notes | AI, double-checked by the product |

| Urgency | Meaning, for any business |
| --- | --- |
| Urgent | Harm happening now to money, data, safety or reputation, or a legal threat |
| High | The customer is stuck with no workaround, or is about to leave |
| Normal | A real question or problem that can wait for today's inbox session |
| Low | Nothing to fix: ideas, praise, general feedback |

| Anger | Label | Signals in the text |
| --- | --- | --- |
| 1 | Calm | Neutral or polite, even when the issue is serious |
| 2 | Mildly frustrated | Disappointed but cooperative |
| 3 | Frustrated | Clear complaint, blame on the business, impatience |
| 4 | Angry | Ultimatums, threats to leave, sarcasm aimed at the business |
| 5 | Extremely angry | Hostility, swearing, all-caps, threats to go public or legal |

An email's status moves only through the owner's rules and the owner's own actions; the AI never sets it.

*(Diagram in the original doc: ticket lifecycle · 8 states, 1 decision.)*

"Urgent, alert sent" is the only status where an email waits on the owner's decision; marking it not urgent moves it to the inbox and saves the change as a correction.

## When the owner gets alerted

The owner gets an alert only when an email is urgent, when the customer is extremely angry, or when one of their own rules says so; everything else waits for their next inbox session. With one person, every alert costs focus, so alerts are treated as a budget, not a default.

| Order | Check (first match wins) | What happens |
| --- | --- | --- |
| 1 | Safety floor: violence or self-harm, hacked account or data leak, legal threat | Alert now, always, even in quiet hours |
| 2 | The owner's rules | Whatever the rule says; the most urgent result wins |
| 3 | Urgent, or anger 5 | Alert now |
| 4 | Anger 4 from an important contact, a customer about to cancel, or a third email about the same thing | Alert now |
| 5 | The AI could not read the email, or is unsure | "Needs a look" list, no alert |
| 6 | Spam or not for me | Closed, still findable |
| 7 | Everything else | Inbox, sorted by urgency, then anger, then age |

Making alerts work for one person:

- **Everything needed is in the alert:** the summary, the quoted lines and the rule that fired, so the owner can decide from their phone.
- **One tap to answer:** "On it" moves the email to in progress; "Not urgent" moves it to the inbox and saves a correction.
- **One reminder, then quiet:** if an alert is not opened within a time the owner picks, one reminder follows, never a stream of pings.
- **Quiet hours:** outside working hours, only the safety floor and rules marked "even at night" alert; the rest waits for the morning.
- **Morning summary:** one message a day with what arrived, what needs a look and anything unusual.

*(Diagram in the original doc: severity × anger · one example email per quadrant.)*

Three of the four corners reach the owner at once; routine emails wait for the next inbox session, and moderate anger alerts only when a rule or an important contact says so.

## Principles

The idea everything else follows from: the AI reads and suggests, but the owner's rules decide what happens. Each principle below is something the demo should be able to show.

- **The AI suggests, rules decide.** The AI writes notes on each email; plain rules turn those notes into an outcome. The owner can always see which rule fired and why.
- **The owner's rules, in the owner's words.** Rules are written as sentences and shown back as readable cards, not codes or pages of switches.
- **A safety floor nobody can switch off.** Owner rules can make things more urgent, never less urgent than the floor.
- **Test before trust.** Every new rule is tried on past emails before it goes live, so the owner sees its effect first.
- **Two ways to catch the dangerous ones.** A simple word check for legal, security and safety terms runs beside the AI, and either can raise the alarm. One AI mistake, or an email written to fool it, is not enough to bury a real threat.
- **Missing an urgent email is worse than a false alarm, but alerts are a budget.** Both are measured and shown side by side.
- **When unsure, ask the owner.** If the AI cannot read an email or is not confident, it lands in "Needs a look", never silently in the normal pile.
- **Show the proof.** Every note comes with the exact lines from the email behind it.
- **Every correction teaches.** A changed label is kept as an example for that business, and repeated corrections turn into a suggested rule.

## Feature list

Twelve must-ship features make one complete loop: set up a business, write a rule, an email arrives and gets its notes, the owner is alerted and answers, and the score report shows it works for more than one business. Differentiators are where the take-home stands out; pick two or three.

| Feature | What it does | Tier | Status |
| --- | --- | --- | --- |
| Business setup | Profile, topics and important contacts, in plain words | Must ship | Not started |
| Starter templates | Online shop, appointments business and software subscription, each with topics, rules and sample emails | Must ship | Not started |
| Rule builder | Write "when ... then ..." rules in plain words; shown back as readable cards | Must ship | Not started |
| Rule test | Run a new rule on past emails and see what would change before saving | Must ship | Not started |
| Safety floor and word check | Built-in alerts for safety, security, data and legal threats, caught by the AI or a simple word check | Must ship | Not started |
| AI notes | Topic, urgency, anger, risk flags, summary and proof on every email, through the LangGraph pipeline | Must ship | Not started |
| Inbox | Sorted list with urgent emails at the top; filters by topic, urgency and status | Must ship | Not started |
| Email detail | The email with the proof highlighted, every note with its reason, and the rule that fired | Must ship | Not started |
| Alert with one-tap answers | Phone or email alert with the summary; "On it" or "Not urgent" in one tap | Must ship | Not started |
| Needs a look | Emails the AI could not read or was unsure about, with the reason | Must ship | Not started |
| Test emails and score report | Sample emails with known answers for each business type; report on missed urgent emails, false alarms and topic accuracy | Must ship | Not started |
| Write-up and demo video | Decisions, trade-offs, scores and next steps; a 3-minute walkthrough | Must ship | Not started |
| Morning summary | One message a day: what arrived, what needs a look, anything unusual | Differentiator | Not started |
| Quiet hours and reminders | Outside working hours only the safety floor alerts; one reminder for an unopened alert | Differentiator | Not started |
| Rule suggestions | Repeated corrections turn into "make this a rule?" | Differentiator | Not started |
| Overview | Emails by topic, alerts this week, anger trend | Differentiator | Not started |
| Live updates | New emails appear without refreshing the page | Differentiator | Not started |
| Thread awareness | Judge only the newest message in a thread; check again on every reply | Differentiator | Not started |
| Real inbox connection | Gmail or Outlook | Roadmap only | Not started |
| Reply drafts | Suggested replies for routine emails; the owner sends | Roadmap only | Not started |
| More languages | Notes in the customer's language instead of "Needs a look" | Roadmap only | Not started |
| Hiding personal data | Mask card numbers, phone numbers and addresses before the AI reads them | Roadmap only | Not started |
| Backup contact | A second person who gets safety alerts when the owner does not respond | Roadmap only | Not started |
| Growing into a team | Hand-off to a helpdesk when the business hires | Roadmap only | Not started |

Cut lines:

- **2 to 3 days:** the must-ship rows, with two starter templates and a plain inbox.
- **5 days:** add the morning summary, quiet hours and reminders, and the overview.
- **A sixth day:** rule suggestions, the clearest sign the product learns each business.
- **Roadmap rows** go in the write-up as "what I would build next", one line each.

## Demo story

The demo is built backwards from four moments a reviewer should remember: the owner writes a rule in plain words, a calm email triggers it, a trick email fails, and the same product serves a second, very different business. Sample data and preset test emails make each moment one click.

1. **Set up in two minutes.** Pick the online shop template, rename it to a bakery, edit the description and add one important contact.
2. **Write a rule.** Type "When an order is for today or tomorrow and something is wrong, alert me." Test it on past emails, see which ones it would have caught, then save.
3. **Calm but urgent.** Send a polite email saying tomorrow's wedding cake still shows as unconfirmed. The owner's rule fires and the phone alert shows the summary, the quoted line and the rule's name.
4. **One tap.** Tap "On it"; the email moves to in progress.
5. **Angry but routine.** Send an all-caps rant about a slightly wrong icing colour. It alerts at anger 5; tap "Not urgent" and show the correction being kept.
6. **Trick email.** Send an email that tells the AI to ignore it and also mentions a stolen card. The safety floor still alerts.
7. **A different business.** Switch to the software subscription template. A polite "all my invoices show zero since your update" is caught by that business's rules, with no change to the product.
8. **Score report.** Missed urgent emails, false alarms and topic accuracy for both businesses side by side.
9. **Close on trade-offs.** Two minutes of the write-up: what was cut, why, and what comes next.

## Success measures

The measure that matters most is missed urgent emails: of the emails that should have alerted the owner, how many did not. False alarms and alerts per day sit right beside it, because for one person an alert that should not have come is also a cost. Targets are proposals to tune after the first score report.

| Measure | In plain words | Proposed target |
| --- | --- | --- |
| Missed urgent emails | Of the emails that should have alerted, how many did not | 5% or fewer |
| False alarms | Of the alerts sent, how many the owner marked "Not urgent" | Shown; aim for 30% or fewer |
| Alerts per day | How often the owner is interrupted | Shown on the overview |
| Topic accuracy | Emails filed under the right topic | 85% or more |
| Needs a look | Share of emails sent to the owner because the AI was unsure | Under 10% |
| Corrections | How often the owner changes a note | Falling over time |
| Time to alert | Email arrives to alert sent | Under a minute |
| Judgement rule accuracy | How often the AI's yes or no on a judgement rule matches the right answer on test emails | 90% or more |

Test emails:

- About 50 to 70 per business type across three types, hand-checked, with roughly a quarter that should alert.
- Every hard case gets several examples: calm but urgent, angry but routine, sarcasm, trick emails, long threads, auto-replies, other languages.
- The same scoring runs for every business type; good scores on all three are the proof that the platform is business agnostic.
- Emails written with an AI's help are checked by hand before they count, so the AI is not marking its own homework.

## Risks and edge cases

Letting the owner write rules adds a new kind of risk on top of the usual tricky emails: a rule that is too loose, too tight or badly worded. The first five rows are about rules; the rest are emails that look like one thing and are another. Each one goes into the test emails.

| Case | What goes wrong | How the product handles it |
| --- | --- | --- |
| A rule that is too broad | The owner is buzzed all day | The rule test shows the alert count before saving; alerts per day on the overview |
| A rule that is too narrow or badly worded | Urgent emails slip past | Built-in alerts still apply beneath it; the score report shows each rule's hits |
| Two rules disagree | An unclear outcome | The most urgent result wins; the email shows both rules |
| A rule tries to silence safety | A real threat is missed | Not possible: the safety floor sits beneath every rule |
| The owner is asleep or away | An urgent alert sits unseen | One reminder; the morning summary leads with it; a backup contact is on the roadmap |
| Calm but urgent | A polite tone hides a disaster | Urgency and anger are noted separately |
| Angry but routine | Every rant becomes an alert | Anger 4 alerts only with a reason; one-tap "Not urgent" |
| Sarcasm | "Great, a third week without my order" reads as happy | Sarcasm examples in the test emails |
| Trick emails | The email tells the AI to ignore it | Email text is treated as content, never as instructions; the word check runs on its own |
| Long threads | Old anger counts again | Only the newest message is judged; the rest is background |
| Auto-replies, newsletters, phishing | Clutter | "Spam or not for me", closed but findable |
| Other languages | Wrong notes | Sent to "Needs a look" |
| The AI service is down | Nothing gets sorted | Emails wait in "Needs a look"; the inbox still works |
| Customer data sent to an AI provider | Privacy | Said plainly in the write-up; hiding personal data is on the roadmap |

## Prior art and how to stand out

Existing tools are built either for support teams or for one person's private inbox; a business inbox run by one owner with their own rules sits between the two. That gap is the story to tell.

| Reference | What it does | What to borrow | Where this build goes further |
| --- | --- | --- | --- |
| [Zendesk intelligent triage](https://support.zendesk.com/hc/en-us/articles/5201262314266-Analyzing-intelligent-triage-classifications) | Sorts support tickets by topic, sentiment and language for teams; Zendesk puts the saving at 30 to 60 seconds a ticket | Agents can correct labels and managers review those corrections ([Zendesk](https://support.zendesk.com/hc/en-us/articles/6298065502874-Configuring-how-agents-can-see-and-update-intelligent-triage-fields)) | Built for one owner and any business; urgency kept apart from mood |
| [Zendesk escalation guide](https://support.zendesk.com/hc/en-us/articles/6353620565530-Using-intelligent-triage-to-identify-and-act-on-ticket-escalations) | Admins set up escalation rules on top of the AI's labels | Rules on top of labels | Rules in plain words, tested before they go live |
| [LangChain agents-from-scratch](https://github.com/langchain-ai/agents-from-scratch) | A personal email assistant that sorts mail, drafts replies and asks before acting | Ask before acting; a test set from day one | Customers, urgency and alerts, set up by the business owner |

How to stand out:

- **Do not rebuild the LangChain tutorial.** Reviewers who use LangGraph will know it.
- **Lead the write-up with decisions:** one owner, any business, rules in their words, a safety floor nobody can switch off.
- **Show two businesses in the demo.** That is the proof of "business agnostic".
- **Tell your own version of the core idea.** At Bull Agritech the CRM agents cannot corrupt the CRM's records; here, the AI cannot change an email's status on its own.

## Open questions and next step

The answers to these change the cut line or the rule design, so they are worth one email to the recruiter before building.

- What is the time budget and the deadline?
- Does "status" in the brief mean where the email stands, its topic, or both? If no answer, the write-up states the reading in Context.
- Should rules be fully free text, or is a guided "when ... then ..." form fine? The form is easier to test and explain.
- Is a hosted demo expected, or a repo they run locally?
- Will they supply sample emails, or is made-up data fine?
- Which AI providers are allowed, and is there a cost ceiling?
- Which Clarity is this? Searches did not confirm a company at clarity.tech; the closest matches are Clarity AI (sustainability data, clarity.ai) and Clarity (deepfake detection, getclarity.ai). Knowing their product would help pick the starter templates.

Next step: the technical design, kept to what this build needs and tied back to the principles above.

## Sources

- [Zendesk: Analyzing intelligent triage classifications](https://support.zendesk.com/hc/en-us/articles/5201262314266-Analyzing-intelligent-triage-classifications)
- [Zendesk: Configuring how agents can see and update intelligent triage fields](https://support.zendesk.com/hc/en-us/articles/6298065502874-Configuring-how-agents-can-see-and-update-intelligent-triage-fields)
- [Zendesk: Using intelligent triage to identify and act on ticket escalations](https://support.zendesk.com/hc/en-us/articles/6353620565530-Using-intelligent-triage-to-identify-and-act-on-ticket-escalations)
- [LangGraph docs: Interrupts](https://docs.langchain.com/oss/langgraph/interrupts)
- [LangChain: agents-from-scratch](https://github.com/langchain-ai/agents-from-scratch)
