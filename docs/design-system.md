# Herald: Design System

Herald's look is direction **M, "Control room"**, picked on 2026-11-03 from the [design canvas](https://claude.ai/artifact/WmiNnvDNj9HEW8Kh468H72) (round 4). It borrows how PostHog's product feels (dense, keyboard-first, pressable buttons, dashed dividers, plain solid surfaces) with a palette of its own: cool concrete, ink and one loud chartreuse.

The design has one job: show the owner that their support agent is keeping the mailbox clean. Every screen answers three questions in order: what needs me now, why Herald thinks so, and what it already handled.

| Where | What |
| --- | --- |
| `apps/web/src/lib/styles/tokens.css` | Every colour, size, space, radius and motion value, in light and dark |
| `apps/web/src/lib/styles/base.css` | Page basics: font, background, focus ring, reduced motion |
| `apps/web/src/lib/ui/` | The components (`Button`, `Tag`, `StatusTag`, `AngerMeter`, `Tabs`, `FilterChip`, `Panel`, `Kbd`, `Icon`) and `tones.ts` |
| `/design-system` in the web app | The gallery: every token and component, with a light and dark switch |

## Principles

1. **One loud colour, and it means "act here".** Chartreuse is only for the primary action, the selected row or tab, and text selection. It never shows a status.
2. **Status has its own colours.** Red for needs you now, amber for needs a look, green for in progress, grey for everything Herald already handled. A status always shows its words too, never colour alone.
3. **Show the proof.** Any note Herald writes (urgency, anger, a rule that fired) sits next to the line from the email behind it.
4. **The safety floor looks different from everything else.** Ink with chartreuse in light mode, inverted in dark. Nothing else uses that pair, and no rule or setting hides it.
5. **Dense, not cramped.** 13 px tables, 42 px rows, 32 px controls. Density comes from fewer decorations, not smaller targets.
6. **Solid surfaces.** No gradients, no glass, no shadows except on things that float (menus, toasts, popovers).
7. **Keyboard first.** Every owner action has a shortcut, and the button shows it.

## Tokens

Components use **semantic tokens** only (`--color-*`, `--tone-*`, `--text-*`, `--space-*`, `--radius-*`). The primitives (`--concrete-*`, `--chartreuse-*`, `--red-*`, ...) exist so the semantic layer has one source; don't use them in a component. If no semantic token fits, add one to `tokens.css`, in both themes, and list it here.

### Colour

| Token | Light | Dark | Use for |
| --- | --- | --- | --- |
| `--color-bg` | `#E6E8EC` concrete | `#121418` | The page behind panels |
| `--color-surface` | `#FFFFFF` | `#1A1D22` | Panels, tables, side panels |
| `--color-surface-sunken` | `#F6F7F9` | `#16181C` | The icon rail, table headers |
| `--color-surface-muted` | `#EEF0F3` | `#23272E` | Inactive tabs, hover on quiet buttons |
| `--color-text` | `#15171C` ink | `#ECEEF1` | Headings, names, labels |
| `--color-text-body` | ink at 88% | light at 88% | Paragraphs and email text |
| `--color-text-muted` | `#5B606B` | `#A3A9B4` | Times, meta, captions |
| `--color-border` | `#D9DCE2` | `#2C3038` | Solid edges of panels, tables, tabs |
| `--color-border-dashed` | `#CDD1D8` | `#3A3F48` | Dashed dividers inside a panel, table row rules |
| `--color-border-control` | `#7B818B` | `#6A707B` | Inputs, filter chips, secondary buttons (3:1 against the surface) |
| `--color-accent` | `#C5EE3F` chartreuse | same | Primary button face, selected tab, selection |
| `--color-accent-base` / `-edge` | `#7E9A1E` / `#4F6312` | `#6E8719` / `#3E4E0E` | The base and outline under a primary button |
| `--color-accent-soft` | `#FBFDF3` | `#1D2312` | Background of the selected row |
| `--color-on-accent` | ink | ink | Text on chartreuse, always ink, never white |
| `--color-live` | `#1F9D6A` | same | The "Herald is reading" dot only |

### Tones: status, urgency and flags

Each tone is a `-bg` and `-fg` pair. The mapping lives in `apps/web/src/lib/ui/tones.ts`. Use `StatusTag` or the `STATUS` and `URGENCY` maps; don't pick a tone by hand for an email.

| Tone | Status | Urgency | Other |
| --- | --- | --- | --- |
| `danger` | Needs you now (`alerted`) | Urgent | |
| `warning` | Needs a look (`needs_a_look`) | High | |
| `success` | In progress (`in_progress`) | | |
| `neutral` | Inbox (`inbox`) | Normal | About to cancel |
| `muted` | Done, Closed quietly, Reading (`new`) | Low | |
| `floor` | | | Safety floor flags only |
| `accent` | | | Important contact only |

The status words are fixed: **Needs you now, Needs a look, Inbox, In progress, Done, Closed quietly, Reading.** Use them in tags, tabs, filters and copy alike.

### Type

One family: **Albert Sans** (variable, self-hosted through `@fontsource-variable/albert-sans`). All figures are tabular.

| Token | Size | Weight | Use for |
| --- | --- | --- | --- |
| `--text-4xl` | 42 | 800, tracking −0.03em | Display. At most once per screen, often never |
| `--text-3xl` | 30 | 800 | Hero numbers ("3 need you now") |
| `--text-2xl` | 24 | 800 | Page titles |
| `--text-xl` | 18 | 800 | Side panel titles (the open email's subject) |
| `--text-lg` | 16 | 700 | Row titles in cards and lists |
| `--text-md` | 14 | 400 to 700 | Body, buttons. The default |
| `--text-sm` | 13 | 400 to 700 | Table cells, meta, filter chips |
| `--text-xs` | 12 | 600 to 700 | Tags, table headers, kbd |

- Sentence case everywhere: headings, buttons, tabs, table headers. No all-caps labels.
- Body text uses `--color-text-body` (ink at 88%), not a third grey. Prefer opacity to new colours.
- Don't go below 12 px. Don't use more than three sizes in one panel.

### Space, shape and size

- **Space** is a 4 px scale: `--space-1` (4) to `--space-12` (48). Panel padding is `--space-4`; gaps between panels are `--space-4`; gaps inside a row of controls are `--space-2`.
- **Radius** follows the size of the thing: `--radius-xs` 4 (tags, kbd), `--radius-sm` 7 (inputs, chips), `--radius-md` 8 (buttons, tabs), `--radius-lg` 10 (panels, tables), `--radius-xl` 14 (dialogs). Never one radius on everything.
- **Borders:** 1 px solid for the edge of a container, 1 px **dashed** for dividers inside one (panel header, table rows). 1.5 px only for pressable buttons.
- **Sizes:** controls `--control-md` 32, rail items `--control-lg` 40, table rows `--row-height` 42, tabs `--tab-height` 34, rail `--rail-width` 56, side panel `--panel-width` 352.

## Components

### Button: it presses down

A raised face sits `--press-depth` (3 px) above a darker base. On click it drops to 1 px. On hover nothing moves: snappy in, eased out on release, as PostHog does it.

| Variant | Use | Rule |
| --- | --- | --- |
| `primary` | The one main action in the current view (**On it** for an alerted email, **Save rule**) | At most one per view. Chartreuse face, ink text |
| `secondary` | Every other action (**Not urgent**, **Done**, **Test on past emails**) | White face, 3:1 edge |
| `quiet` | Low-stakes actions and links in toolbars (**Open thread**) | No base, no press |

- Pass `kbd` to show the shortcut. The owner actions are fixed: **O** On it, **N** Not urgent, **D** Done, **Z** Undo, **/** Search. Wiring the key is the screen's job; the button only shows it.
- Labels say what happens, and the result uses the same words: the button **Not urgent** gives a toast "Moved to Inbox. Herald saved this as a correction."
- There is no destructive red button. Herald never deletes; closing is reversible.

### Tag and StatusTag

Small, 20 px tall, `--radius-xs`. Use `StatusTag` for an email's status so the colour and words can't drift. Add an icon only to the safety floor (`shield`). Tags are not buttons; for something clickable, use a `FilterChip`.

### AngerMeter

Five bars, filled with ink. Anger is never shown with urgency colours: a calm email can be urgent and a furious one can be routine. The meter's accessible name is "Anger 4 of 5, angry" (`angerLabel`). Use `showLabel` wherever there is room (side panels); in tables the bars alone are fine because the name is still announced.

### Tabs

Browser-style tabs across the top of a view. A tab can carry a count (`Tag`), with a danger tone only for **Needs you**. Arrow keys move between tabs. Opening an email or a rule test may open a new tab, as PostHog does.

### FilterChip

Dashed when off, solid ink when on (`aria-pressed`). Chips filter the current view; they never navigate.

### Panel

White surface, 1 px border, `--radius-lg`. An optional header with a title and actions sits above a dashed divider. Don't nest panels.

### Icon

Line icons on a 24 px grid, 1.8 stroke, `currentColor`. Add new glyphs to `Icon.svelte`; don't paste SVG into screens. An icon next to a label is decoration (hidden from screen readers); an icon alone needs `label`. No emoji.

## Patterns

- **The inbox** is a table: Status, From, Summary, Topic, Urgency, Anger, Why, Time. Sorted by urgency, then anger, then age, as the decide step orders them. The selected row gets `--color-accent-soft` and a chartreuse edge.
- **The side panel** explains the open email: the safety floor callout first if there is one, then the quoted line with the proof highlighted (`--color-accent-tint` with an olive underline), then the notes, then the actions at the bottom.
- **The safety floor callout** is a `--tone-floor-bg` block with the `shield` icon and one sentence: "Safety floor: legal threat. This always alerts you, whatever your rules say."
- **What Herald handled** is always one line, never hidden: "Also today: 18 in the inbox, 2 in progress, 40 closed quietly." with a link to see them.
- **Live** is the green dot with "Tripfold, live". Nothing else animates on its own.
- **Empty states** tell the owner what happens next: "Nothing needs you. Herald will buzz your phone if something urgent arrives."

## Copy

- Herald speaks plainly, in the second person, about the owner's mail: "Herald saved this as a correction." Not "Correction recorded successfully."
- Name things the way the docs do: notes, rules, safety floor, important contacts, needs a look. Never "webhook", "pipeline", "LLM" or "classification" in the interface.
- Quote the customer exactly, in quotation marks. Never paraphrase a quote.
- Herald never replies to customers or touches money. Copy never suggests it does.
- Sample data (fixtures, screenshots, the gallery) uses Tripfold and specific, believable emails, as in `apps/server/src/herald_server/seed.py`. Make it real enough to smile at, never lorem ipsum.

## Accessibility

- Text pairs are 4.5:1 or better in both themes, checked when the tokens were set (ink on concrete 14.6:1, muted on white 6.3:1, every tone pair 5.5:1 or better). Control edges are 3:1. Recheck any new pair before adding it.
- Colour never carries meaning alone: tags have words, the anger meter has a name, the selected row has an edge.
- Every interactive thing is a real `<button>`, `<a>` or `<input>` with a visible `:focus-visible` ring (`--color-focus`, 2 px, offset 2 px).
- Targets are at least 24 px (WCAG 2.2 AA); owner actions use the 32 px button.
- `prefers-reduced-motion` turns transitions and animations off (`base.css`).

## Dark mode

Both themes ship together. The page follows the system setting; `data-theme="light"` or `"dark"` on `<html>` overrides it. Every new semantic token needs a dark value in both dark blocks of `tokens.css` (the media query and the `data-theme` rule). In dark, chartreuse stays the same and the safety floor inverts to chartreuse with ink.

## Adding to the system

1. Check the gallery first: the thing may already exist.
2. New value: add a semantic token to `tokens.css` in light and both dark blocks, check its contrast, and add a row to the tables above.
3. New component: put it in `apps/web/src/lib/ui/`, export it from `index.ts`, add it to the gallery, and describe its rules here.
4. A screen that needs a one-off style probably needs a token or a variant instead.
