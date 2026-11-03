# Herald: Design System

Herald's look is direction **M, "Control room"**, picked on 2026-11-03 from the [design canvas](https://claude.ai/artifact/WmiNnvDNj9HEW8Kh468H72) (round 4). It borrows how PostHog's product feels (dense, keyboard-first, pressable buttons, dashed dividers, plain solid surfaces) with a palette of its own: cool concrete, ink and one loud chartreuse.

The design has one job: show the owner that their support agent is keeping the mailbox clean. Every screen answers three questions in order: what needs me now, why Herald thinks so, and what it already handled.

The web app styles everything with **Tailwind CSS v4**, and the tokens below are Tailwind's theme.

| Where | What |
| --- | --- |
| `apps/web/src/lib/styles/tokens.css` | The Tailwind theme (`@theme`): every colour, type size, radius, size and shadow, plus the dark values |
| `apps/web/src/app.css` | Imports Tailwind, the font and the tokens; page basics (font, background, focus ring, reduced motion) |
| `apps/web/src/lib/ui/` | The components (`Button`, `Tag`, `StatusTag`, `AngerMeter`, `Tabs`, `FilterChip`, `Panel`, `Kbd`, `Toast`, `Icon`, `Logo`) and `tones.ts` |
| `apps/web/src/lib/inbox/` | The inbox built from them: `EmailTable`, `EmailPanel` and `inbox.ts` (views, order, actions, proof highlighting) |
| `/design-system` in the web app | The gallery: every token and component, with a light and dark switch |

## Principles

1. **One loud colour, and it means "act here".** Chartreuse is only for the primary action, the selected row or tab, and text selection. It never shows a status.
2. **Status has its own colours.** Red for needs you now, amber for needs a look, green for in progress, grey for everything Herald already handled. A status always shows its words too, never colour alone.
3. **Show the proof.** Any note Herald writes (urgency, anger, a rule that fired) sits next to the line from the email behind it.
4. **The safety floor looks different from everything else.** Ink with chartreuse in light mode, inverted in dark. Nothing else uses that pair, and no rule or setting hides it.
5. **Dense, not cramped.** 13 px tables, 42 px rows, 32 px controls. Density comes from fewer decorations, not smaller targets.
6. **Solid surfaces.** No gradients, no glass, no shadows except on things that float (menus, toasts, popovers).
7. **Keyboard first.** Every owner action has a shortcut, and the button shows it.

## Using Tailwind here

- **Only Herald's tokens exist.** `tokens.css` switches off Tailwind's default colours, font sizes, radii and shadows (`--color-*: initial` and so on). `bg-red-500` or `text-base` will not work; `bg-danger-bg` and `text-md` will. That is on purpose: a screen can't drift off the palette.
- **Spacing is Tailwind's 4 px scale** (`p-4` is 16 px, `gap-2` is 8 px). Use the scale, not arbitrary values. Herald adds a few named sizes: `h-control-md`, `h-row`, `h-tab`, `w-rail`, `w-rail-wide`, `w-panel`.
- **No `<style>` blocks in components.** Write utilities in `class`. Use Svelte's array or object `class` syntax for variants (`class={['…', active && '…']}`).
- **Variants live in a lookup, not in string building.** Write whole class names (`'bg-danger-bg text-danger-fg'`), never `bg-${tone}-bg`: Tailwind only finds classes it can read in full. `TONE_CLASSES` in `tones.ts` is the pattern.
- **Arbitrary values are a last resort.** If you reach for `[…]` twice for the same thing, add a token instead.
- **Don't use the `dark:` variant.** Dark mode works by redefining the token variables, so `bg-surface` is already right in both themes.
- **Class order is Prettier's.** `prettier-plugin-tailwindcss` sorts classes on `pnpm format`.

## Tokens

### Colour

| Utility (`bg-`, `text-`, `border-`) | Light | Dark | Use for |
| --- | --- | --- | --- |
| `canvas` | `#E6E8EC` concrete | `#121418` | The page behind panels |
| `surface` | `#FFFFFF` | `#1A1D22` | Panels, tables, side panels |
| `sunken` | `#F6F7F9` | `#16181C` | The icon rail, table headers |
| `subtle` | `#EEF0F3` | `#23272E` | Inactive tabs, hover on quiet buttons |
| `ink` | `#15171C` | `#ECEEF1` | Headings, names, labels |
| `body` | ink at 88% | light at 88% | Paragraphs and email text |
| `muted` | `#5B606B` | `#A3A9B4` | Times, meta, captions |
| `line` | `#D9DCE2` | `#2C3038` | Solid edges of panels, tables, tabs |
| `line-dashed` | `#CDD1D8` | `#3A3F48` | Dashed dividers inside a panel, table row rules |
| `control` | `#7B818B` | `#6A707B` | Edges of inputs, filter chips, secondary buttons (3:1) |
| `accent` | `#C5EE3F` chartreuse | same | Primary button face, selected tab, selection |
| `accent-base`, `accent-edge` | `#7E9A1E`, `#4F6312` | `#6E8719`, `#3E4E0E` | The base and outline under a primary button |
| `accent-soft` | `#FBFDF3` | `#1D2312` | Background of the selected row |
| `accent-tint` | `#F3FAD9` | `#263015` | Highlighted proof in an email, important contact tag |
| `on-accent` | ink | ink | Text on chartreuse: always ink, never white |
| `focus` | ink | chartreuse | The focus ring |
| `live` | `#1F9D6A` | same | The "Herald is reading" dot only |
| `logo-tile`, `logo-edge`, `logo-row` | `#15171C`, `#15171C`, white at 40% | `#23272E`, `#3A3F48`, same | The logo only (`Logo`). Nothing else uses them |

### Tones: status, urgency and flags

Each tone is a `-bg` and `-fg` pair (`bg-danger-bg text-danger-fg`). The mapping lives in `apps/web/src/lib/ui/tones.ts`. Use `StatusTag`, or the `STATUS`, `URGENCY` and `TONE_CLASSES` maps; don't pick a tone by hand for an email.

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

One family: **Schibsted Grotesk** (variable, self-hosted through `@fontsource-variable/schibsted-grotesk`). It was drawn for news reading at small sizes, stays firm in dense tables and has a real 800 weight. Each size carries its own line height.

One mono: **JetBrains Mono** (`@fontsource-variable/jetbrains-mono`), through `font-mono`. Use it only for things people copy or type: shortcut keys (`Kbd` uses it), order IDs and email addresses. Never for body text or for numbers in tables.

Figures are proportional by default. Add `tabular-nums` only where a column holds nothing but digits, such as counts. Schibsted's tabular set also widens `, . : ; # %`, so on times ("9:47 am"), amounts ("₹6,499") or prose it puts gaps around the punctuation. That is why `body` does not set it.

A replacement face must have tabular figures (`tnum`), its own ₹ and weights up to 800. Albert Sans was dropped because it has no tabular figures at all.

| Utility | Size | Weight | Use for |
| --- | --- | --- | --- |
| `text-4xl` | 42 | `font-extrabold tracking-display` | Display. At most once per screen, often never |
| `text-3xl` | 30 | `font-extrabold tracking-display` | Hero numbers ("3 need you now") |
| `text-2xl` | 24 | `font-extrabold` | Page titles |
| `text-xl` | 18 | `font-extrabold` | Side panel titles (the open email's subject) |
| `text-lg` | 16 | `font-bold` | Row titles in cards and lists |
| `text-md` | 14 | regular to bold | Body, buttons. The default |
| `text-sm` | 13 | regular to bold | Table cells, meta, filter chips |
| `text-xs` | 12 | `font-semibold` or `font-bold` | Tags, table headers, kbd |

- Sentence case everywhere: headings, buttons, tabs, table headers. No all-caps labels.
- Body text uses `text-body` (ink at 88%), not a third grey. Prefer opacity to new colours.
- Don't go below 12 px. Don't use more than three sizes in one panel.

### Shape and size

- **Radius** follows the size of the thing: `rounded-xs` 4 (tags, kbd), `rounded-sm` 7 (inputs, chips), `rounded-md` 8 (buttons, tabs), `rounded-lg` 10 (panels, tables), `rounded-xl` 14 (dialogs). Never one radius on everything.
- **Borders:** `border border-line` for the edge of a container; `border-dashed border-line-dashed` for dividers inside one (panel header, table rows); `border-[1.5px]` only for pressable buttons.
- **Sizes:** `h-control-md` 32 (inputs, chips), `size-control-lg` 40 (rail items), `h-row` 42 (table rows), `h-tab` 34, `w-rail` 56 (the closed rail), `w-rail-wide` 208 (the rail with labels), `w-panel` 352 (the detail side panel).
- **Shadow:** `shadow-popover`, only on things that float.

## Components

### Button: it presses down

A raised face sits `--press-depth` (3 px) above a darker base. On click it drops to 1 px. On hover nothing moves: snappy in, eased out on release, as PostHog does it.

| Variant | Use | Rule |
| --- | --- | --- |
| `primary` | The one main action in the current view (**On it** for an alerted email, **Save rule**) | At most one per view. Chartreuse face, ink text |
| `secondary` | Every other action (**Not urgent**, **Done**, **Test on past emails**) | White face, 3:1 edge |
| `quiet` | Low-stakes actions and links in toolbars (**Open thread**) | No base, no press |

- Pass `kbd` to show the shortcut. The owner actions are fixed: **O** On it, **N** Not urgent, **I** Move to Inbox, **D** Done, **E** read the whole email, **/** Search, **J** and **K** next and previous email. Wiring the key is the screen's job; the button only shows it.
- Labels say what happens, and the result uses the same words: the button **Not urgent** gives the message "Moved to Inbox. Herald saved this as a correction."
- There is no destructive red button. Herald never deletes; closing is reversible.

### Tag and StatusTag

Small, 20 px tall, `rounded-xs`. Use `StatusTag` for an email's status so the colour and words can't drift. Add an icon only to the safety floor (`shield`). Tags are not buttons; for something clickable, use a `FilterChip`.

### AngerMeter

Five bars, filled with ink. Anger is never shown with urgency colours: a calm email can be urgent and a furious one can be routine. The meter's accessible name is "Anger 4 of 5, angry" (`angerLabel`). Use `showLabel` wherever there is room (side panels); in tables the bars alone are fine because the name is still announced.

### Tabs

Browser-style tabs across the top of a view. A tab can carry a count (`Tag`), with a danger tone only for **Needs you**. Arrow keys move between tabs.

### FilterChip

Dashed when off, solid ink when on (`aria-pressed`). Chips filter the current view; they never navigate.

### Panel

`bg-surface`, `border-line`, `rounded-lg`. An optional header with a title and actions sits above a dashed divider. `padded={false}` for edge-to-edge content such as a table. Don't nest panels.

### HoverCard

Help that would clutter the screen, opened from a dotted-underlined label with an `info` icon. Pass `info` to `Panel` to put it on the title. It opens on hover, on focus and on tap (there is no hover on a phone), stays open while the pointer moves into it, and Escape closes it. Say what the thing is for, then what it needs: required or optional, and its limits. Never put the only copy of something the owner must know in a hover card.

### Toast

A short message after an owner action, bottom centre, ink on canvas. It uses the action's own words ("Moved to In progress.") and clears itself after 5 seconds. It sits in a `role="status"` region so screen readers hear it. Errors are not toasts: they stay on screen as a `role="alert"` banner until dismissed.

### ThemeSwitch

Three buttons, System, Light and Dark, each with `aria-pressed`, so the current choice always shows. Don't make it one button that cycles. `labelled` shows the words (the gallery), the default is icons only (the open rail), and `vertical` stacks them (the closed rail). It reads and saves `prefs.theme`; see Dark mode.

### Rail

The main nav on every app screen (`lib/shell/Rail.svelte`), not on the gallery. Closed it is `w-rail`, icons only, each with `aria-label` and `title`. Open it is `w-rail-wide` with labels. Every item keeps the same 40 px icon column in both states, so the icons stay put while the width animates. The theme switch and the collapse toggle sit at the bottom. The open or closed choice is saved in the browser and starts closed.

### Icon

Line icons on a 24 px grid, 1.8 stroke, `currentColor`. Add new glyphs to `Icon.svelte`; don't paste SVG into screens. An icon next to a label is decoration (hidden from screen readers); an icon alone needs `label`. No emoji.

### Logo

The mark is three emails on a tile, with one pulled out of the pile and lit chartreuse: most mail stays quiet, one thing needs you. It is drawn in three places that must match: `Logo.svelte`, `lib/assets/favicon.svg` and `lib/assets/apple-touch-icon.png`.

- **Shapes:** a 64-unit square tile, `rx` 14.25. Rows are 8 units tall on a 4-unit grid so they land on whole pixels at 16 and 32 px: quiet rows at x 12 (28 and 20 wide), the lit row at x 20, 32 wide.
- **Colour:** chartreuse only ever sits on the tile; on a light surface it disappears. In dark mode the tile lifts to `#23272E` with a `#3A3F48` edge so it doesn't sink into the canvas. The favicon does the same with its own `prefers-color-scheme` block.
- **Sizes:** 34 px in the rail, 16 px as the favicon. Don't use it smaller than 16 px.
- **Wordmark:** "Herald" in Schibsted Grotesk ExtraBold with `tracking-display`, set beside the mark with its type about three quarters of the mark's height (30 px type with a 40 px mark). Never redraw it as an image.
- **Touch icon:** full-bleed, square corners; iOS rounds them.
- Give it `label="Herald"` where it stands alone (the rail); leave the label off next to the word "Herald".

## Patterns

- **The inbox** has tabs per status (Needs you, Inbox, In progress, Done, Closed quietly, All mail) and a table: Status, From, Summary, Topic (wide screens only), Urgency, Anger, Why, Time. Sorted by status, then urgency, then anger, then newest, the way the decide step orders them. The selected row gets `bg-accent-soft` and a chartreuse edge.
- **The side panel** explains the open email. It is one card on the canvas (`rounded-lg border-line bg-surface`, the table's gap away), with its parts split by dashed dividers, never cards inside it: the subject, then **Why it's here** (the safety floor callout if there is one, the reason in bold, Herald's summary, the quoted lines as proof in `bg-accent-tint`, then the notes), then **The email**, then the actions at the bottom. The email part shows a three-line preview; **E** or "Read it all" opens the whole email with the proof highlighted, and picking another email folds it again. An email with no notes (Herald is still reading, or the AI failed) opens in full, because there is no summary to read instead.
- **The safety floor callout** is a `bg-floor-bg text-floor-fg` block with the `shield` icon and one sentence: "Safety floor: legal threat. This always alerts you, whatever your rules say."
- **What Herald handled** is always one line, never hidden: "Also today: 18 in the inbox, 2 in progress, 40 closed quietly." with a way to see them.
- **Live** is the `live` dot with "Live". Nothing else in the app animates on its own.
- **The error page** (`routes/+error.svelte`) is the one playful screen: the logo's lit row has floated out of the pile and a magnifying glass hunts for it (`lib/shell/LostMail.svelte`, animations in `tokens.css`). It names the problem in plain words and always offers the way back to the inbox.
- **Empty states** tell the owner what happens next: "Nothing needs you. Urgent emails will show up here first."

## Copy

- Herald speaks plainly, in the second person, about the owner's mail: "Herald saved this as a correction." Not "Correction recorded successfully."
- Name things the way the docs do: notes, rules, safety floor, important contacts, needs a look. Never "webhook", "pipeline", "LLM" or "classification" in the interface.
- Quote the customer exactly, in quotation marks. Never paraphrase a quote.
- Herald never replies to customers or touches money. Copy never suggests it does.
- Sample data (fixtures, screenshots, the gallery) uses Tripfold and specific, believable emails, as in `apps/server/src/herald_server/seed.py`. Make it real enough to smile at, never lorem ipsum.

## Accessibility

- Text pairs are 4.5:1 or better in both themes, checked when the tokens were set (ink on canvas 14.6:1, muted on surface 6.3:1, every tone pair 5.5:1 or better). Control edges are 3:1. Recheck any new pair before adding it.
- Colour never carries meaning alone: tags have words, the anger meter has a name, the selected row has an edge.
- Every interactive thing is a real `<button>`, `<a>` or `<input>` with a visible focus ring (`focus` colour, 2 px, offset 2 px).
- Targets are at least 24 px (WCAG 2.2 AA); owner actions use the 32 px button.
- `prefers-reduced-motion` turns transitions and animations off (`app.css`).

## Dark mode

Both themes ship together. The page follows the system setting; `data-theme="light"` or `"dark"` on `<html>` overrides it. The owner picks System, Light or Dark with the theme switch (`ThemeSwitch`, in the rail and the gallery). The choice is saved in the browser (`src/lib/prefs.svelte.ts`), and a small script in `app.html` applies it before the first paint so a dark choice never flashes light. System removes the attribute. Every colour token needs a dark value in both dark blocks of `tokens.css` (the media query and the `data-theme` rule). In dark, chartreuse stays the same and the safety floor inverts to chartreuse with ink.

## Adding to the system

1. Check the gallery first: the thing may already exist.
2. New value: add it to `@theme` in `tokens.css` (and to both dark blocks if it's a colour), check its contrast, and add a row to the tables above.
3. New component: put it in `apps/web/src/lib/ui/`, export it from `index.ts`, add it to the gallery, and describe its rules here.
4. A screen that needs a one-off style probably needs a token or a variant instead.
