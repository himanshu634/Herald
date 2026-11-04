# Herald

**An open-source mailbox manager for a business run by one person.**

You answer every customer email yourself. Most can wait for tomorrow. A few can't: the customer at the airport with a broken bag, the order that must arrive before a trip, the email that mentions a lawyer. Herald reads every email as it arrives, tells you which few matter, and leaves the rest sorted for when you sit down to work.

It is free, MIT-licensed and runs on your own machine or server.

## What it does for you

- **Reads every email and writes notes on it.** Topic, urgency, how angry the customer is, risk flags and a one-line summary. Each note quotes the lines from the email that back it up, so you can check the AI's reasoning at a glance.
- **Alerts you only when it should.** An email is alerted when it is urgent, the customer is furious, one of your own rules says so, or it is the third email from the same customer about the same thing in a week. Alerts have their own desk, and the app opens on it: worst first, each with its summary, the quote and the rule that fired.
- **Sorts the rest.** Your inbox lists the most urgent emails first, then by anger, then newest first. One click marks an email "On it", "Not urgent" or "Done".
- **Says when it isn't sure.** An email the AI can't read, or isn't confident about, goes to "Needs a look". When it is unsure, it asks you one question. You answer by adding or fixing a fact or a rule, and Herald reads the email again. The answer helps with the next email of that kind too.
- **Lets you reply where the notes are.** Write a reply in the email's panel and press Send. It goes out from your own Gmail, in the customer's thread.
- **Updates live.** New emails and their notes appear in the open app without a refresh.

## Your business, in your words

Herald knows nothing about your business until you tell it. Describe the business in a few lines and Herald drafts the rest. You check and edit the draft before it goes live. All of it is in plain words:

| Part | Example: Tripfold, an online luggage brand |
| --- | --- |
| A few lines about the business | "We sell cabin and check-in luggage, backpacks and travel accessories online across India. A bad day is a customer at the airport with a broken bag, or a trip tomorrow and no delivery." |
| The topics customers write about | Orders and delivery, Returns and exchanges, Damaged or defective, Corporate gifting, and a few more |
| Facts | "Returns are accepted within 7 days of delivery, unused and with tags." |
| Guidance on how to judge | None in the demo. A wedding caterer might write "Wedding orders are always urgent." |
| Contacts who always matter (set through the API for now) | `corporate-gifts@bigcorp.example` |
| Rules: "when …, then …" | When the customer is travelling in the next 48 hours and the order has not arrived, **alert me** |

A rule can alert you, raise or lower an email's urgency, or close it quietly (courier newsletters, for example). The AI answers each rule's "when" with yes or no and quotes the line that decided it. A bakery, a freelance developer and a small software company each write their own rules. Herald's code stays the same.

## What it will never do

- **It never replies on its own.** You write and send every reply. No AI step can send mail.
- **It never makes money decisions.** Refunds, credits and cancellations stay with you.
- **The AI never decides what happens to an email.** It writes notes. Your rules and your clicks move an email between "needs you now", "in progress" and "done", and you can always see which rule fired.
- **No rule can silence a real threat.** A safety floor sits under every rule and can't be switched off. It catches threats of violence or self-harm, a hacked account or data leak, and legal threats. A word check runs beside the AI, so an email written to trick the AI still alerts you.
- **Alerts stay in the app.** Nothing is pushed to your phone or any outside service.

## Where it is today

Herald is early. Today it has:

- Gmail connect, with live push and a 15-minute catch-up. You can choose to have it read your Spam folder too.
- AI notes, your rules, the safety floor and the alert desk
- AI-drafted setup with an editor for the profile, topics, facts, guidance and rules
- The "unsure" question, and a way to rerun Herald on an email after you change a fact or rule
- Replies written by you and sent from Herald
- A demo business, Tripfold, that you can open in one click

Coming next:

- Sign-in, and a settings page to change a business after setup
- Testing a rule on past emails before it goes live
- Outlook and IMAP
- Quiet hours, one reminder for an unopened alert, and a morning summary

**About your data:** Herald stores your email on your own server. The text of each email is sent to the AI provider you choose (OpenRouter by default, or Anthropic) to write its notes. The only mail that leaves Herald is a reply you write and send, through your own Gmail.

## Try it, run it, help build it

- [docs/development.md](docs/development.md): run Herald on your machine with the Tripfold demo, connect Gmail, or run it on your own server
- [CONTRIBUTING.md](CONTRIBUTING.md): how to propose a change
- [docs/](docs/README.md): scope, decisions, architecture, design system and evals

## License

[MIT](LICENSE)
