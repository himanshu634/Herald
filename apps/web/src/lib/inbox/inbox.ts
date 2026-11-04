// Inbox logic with no UI: which emails a view shows, their order, what the owner can do,
// and which parts of the body to highlight as proof. Kept pure so it is easy to test.
import type { Email, EmailStatus, WorkspaceConfig } from '#lib/api/client.js';
import type { Tone } from '#lib/ui/tones.js';

export type ViewId =
	'alerts' | 'needs-a-look' | 'inbox' | 'in-progress' | 'done' | 'closed' | 'all';

export const VIEWS: {
	id: ViewId;
	label: string;
	statuses: EmailStatus[] | null;
	countTone?: Tone;
}[] = [
	// Alerts are the desk the app opens on, not an inbox tab (INBOX_VIEWS leaves them out).
	{ id: 'alerts', label: 'Alerts', statuses: ['alerted'], countTone: 'danger' },
	{
		id: 'needs-a-look',
		label: 'Needs a look',
		statuses: ['needs_a_look'],
		countTone: 'warning'
	},
	{ id: 'inbox', label: 'Inbox', statuses: ['inbox'] },
	{ id: 'in-progress', label: 'In progress', statuses: ['in_progress'] },
	{ id: 'done', label: 'Done', statuses: ['done'] },
	{ id: 'closed', label: 'Closed quietly', statuses: ['closed'] },
	{ id: 'all', label: 'All mail', statuses: null }
];

/** The inbox's tabs. */
export const INBOX_VIEWS = VIEWS.filter((v) => v.id !== 'alerts');

export const EMPTY: Record<ViewId, string> = {
	alerts: 'No alerts. Herald puts an email here the moment it can’t wait.',
	'needs-a-look': 'Nothing needs a look. Mail Herald couldn’t read shows up here.',
	inbox: 'Your inbox is clear.',
	'in-progress': 'Nothing in progress. Press On it on an email to start it.',
	done: 'Nothing done yet today.',
	closed: 'Nothing closed yet. Newsletters and spam land here without bothering you.',
	all: 'No emails yet. New mail shows up here as Herald sorts it.'
};

const STATUS_RANK: Record<EmailStatus, number> = {
	alerted: 0,
	needs_a_look: 1,
	new: 2,
	in_progress: 3,
	inbox: 4,
	done: 5,
	closed: 6
};

const URGENCY_RANK = { urgent: 0, high: 1, normal: 2, low: 3 } as const;

export function inView(email: Email, view: ViewId): boolean {
	const statuses = VIEWS.find((v) => v.id === view)?.statuses;
	return statuses == null || statuses.includes(email.status);
}

/** The decide step's order: status, then urgency, then anger, then newest first. */
export function compareEmails(a: Email, b: Email): number {
	return (
		STATUS_RANK[a.status] - STATUS_RANK[b.status] ||
		urgencyRank(a) - urgencyRank(b) ||
		(b.notes?.anger ?? 0) - (a.notes?.anger ?? 0) ||
		Date.parse(b.received_at) - Date.parse(a.received_at)
	);
}

function urgencyRank(email: Email): number {
	const urgency = email.decision?.urgency ?? email.notes?.urgency;
	return urgency ? URGENCY_RANK[urgency] : 4;
}

export type Filters = { query: string; urgentOnly: boolean };

export function matches(email: Email, filters: Filters): boolean {
	const query = filters.query.trim().toLowerCase();
	if (query) {
		const haystack = [email.sender, email.subject, email.notes?.summary, email.notes?.topic]
			.join(' ')
			.toLowerCase();
		if (!haystack.includes(query)) return false;
	}
	if (filters.urgentOnly && (email.decision?.urgency ?? email.notes?.urgency) !== 'urgent')
		return false;
	return true;
}

/**
 * Herald is unsure and the owner has not taken the email over. These emails ask the owner a
 * question above every view, whatever the tab and filters, until a re-read settles them or
 * the owner marks them On it or Done. An unsure email can sit in any status decide sets:
 * a close rule or an urgency default wins over "unsure", so one may be closed or alerted.
 */
export function asksOwner(email: Email): boolean {
	return (
		email.notes?.sure === false &&
		email.status !== 'new' &&
		email.status !== 'in_progress' &&
		email.status !== 'done'
	);
}

export function questionsFor(emails: Email[]): Email[] {
	return emails.filter(asksOwner).toSorted(compareEmails);
}

/**
 * The alert desk's queue: every alerted email, in decide's order. No search or Urgent filter,
 * which stay on the URL from the inbox and would hide alerts here. Unsure alerts stay in too:
 * an alert outranks a question, so the desk shows it as an alert with its question attached.
 */
export function alertsFor(emails: Email[]): Email[] {
	return emails.filter((e) => e.status === 'alerted').toSorted(compareEmails);
}

/** The questions the desk lists under its queue. Unsure alerts are already in the queue. */
export function deskQuestionsFor(emails: Email[]): Email[] {
	return questionsFor(emails).filter((e) => e.status !== 'alerted');
}

/**
 * The alert to open after the open one left the queue: the one now at its place, or the last.
 * `index` is where the open alert stood before it left.
 */
export function nextAlert(queue: Email[], index: number): Email | null {
	if (!queue.length) return null;
	return queue[Math.min(Math.max(index, 0), queue.length - 1)];
}

/** The owner's "alert me" rules that matched this email, so the desk can show their words. */
export function firedAlertRules(
	email: Email,
	config: WorkspaceConfig
): NonNullable<WorkspaceConfig['rules']> {
	const ids = email.decision?.fired_rule_ids ?? [];
	return (config.rules ?? []).filter((r) => r.action === 'alert' && ids.includes(r.id));
}

/**
 * An alert rule as the owner would say it: "When the customer threatens a review, alert me."
 * Rules are stored as written, often capitalised and with a full stop, so both are tidied.
 * A leading acronym ("VIP customer…") keeps its capitals.
 */
export function alertRuleSentence(when: string): string {
	const text = when.trim().replace(/[.!\s]+$/, '');
	const keep = /^[A-Z]{2}/.test(text);
	return `When ${keep ? text : text.charAt(0).toLowerCase() + text.slice(1)}, alert me.`;
}

/** The table under the questions. Questions are left out: they are already shown above it. */
export function visibleEmails(emails: Email[], view: ViewId, filters: Filters): Email[] {
	return emails
		.filter((e) => !asksOwner(e) && inView(e, view) && matches(e, filters))
		.toSorted(compareEmails);
}

/** The most facts a business keeps (WorkspaceConfig.facts), and the longest one. */
export const MAX_FACTS = 10;
export const MAX_FACT_LENGTH = 200;

export function countByView(emails: Email[]): Record<ViewId, number> {
	const counts = Object.fromEntries(VIEWS.map((v) => [v.id, 0])) as Record<ViewId, number>;
	for (const email of emails)
		for (const view of VIEWS) if (inView(email, view.id)) counts[view.id]++;
	return counts;
}

export type Action = 'on-it' | 'not-urgent' | 'to-inbox' | 'done';

export const ACTIONS: Record<Action, { label: string; key: string; done: string }> = {
	'on-it': { label: 'On it', key: 'O', done: 'Moved to In progress.' },
	'not-urgent': {
		label: 'Not urgent',
		key: 'N',
		done: 'Moved to Inbox. Herald saved this as a correction.'
	},
	'to-inbox': {
		label: 'Move to Inbox',
		key: 'I',
		done: 'Moved to Inbox. Herald saved this as a correction.'
	},
	done: { label: 'Done', key: 'D', done: 'Marked done.' }
};

/** What the owner can do from each status. The first action is the primary one. */
export function actionsFor(status: EmailStatus): Action[] {
	switch (status) {
		case 'alerted':
			return ['on-it', 'not-urgent'];
		case 'needs_a_look':
		case 'inbox':
			return ['on-it', 'done'];
		case 'in_progress':
			return ['done'];
		case 'closed':
			return ['to-inbox'];
		default:
			return [];
	}
}

/**
 * What the owner can do from the question dialog: the status's own actions, plus Done from
 * any status. Done is the honest way to clear a question about mail a close rule sent to
 * Closed quietly; Move to Inbox would save a correction the owner never meant.
 */
export function questionActionsFor(status: EmailStatus): Action[] {
	const actions = actionsFor(status);
	return actions.includes('done') ? actions : [...actions, 'done'];
}

/**
 * Normalise line endings, drop trailing spaces and cap blank lines at one.
 * The server does this when it reads mail; this also tidies emails stored
 * before it did, whose HTML was flattened with all its source whitespace.
 */
export function tidyBody(body: string): string {
	return (
		body
			// Mail re-encoded more than once can end lines with "\r\r\n"; that is one break.
			.replace(/\r*\n|\r/g, '\n')
			.split('\n')
			.map((line) => line.trimEnd())
			.join('\n')
			.replace(/\n{3,}/g, '\n\n')
			.trim()
	);
}

/** Split the body so the lines Herald quoted as proof can be highlighted. */
export function highlight(body: string, quotes: string[]): { text: string; quoted: boolean }[] {
	const ranges: [number, number][] = [];
	for (const quote of quotes) {
		const text = quote.trim();
		if (!text) continue;
		const start = body.indexOf(text);
		if (start >= 0) ranges.push([start, start + text.length]);
	}
	ranges.sort((a, b) => a[0] - b[0]);

	const parts: { text: string; quoted: boolean }[] = [];
	let at = 0;
	for (const [start, end] of ranges) {
		if (end <= at) continue;
		const from = Math.max(start, at);
		if (from > at) parts.push({ text: body.slice(at, from), quoted: false });
		parts.push({ text: body.slice(from, end), quoted: true });
		at = end;
	}
	if (at < body.length) parts.push({ text: body.slice(at), quoted: false });
	return parts;
}

const FLOOR_LABELS: Record<string, string> = {
	safety: 'safety',
	account_or_data: 'hacked account or data',
	legal_threat: 'legal threat'
};

export function floorLabel(flags: string[]): string | null {
	const names = flags.map((f) => FLOOR_LABELS[f]).filter(Boolean);
	return names.length ? `Safety floor: ${names.join(', ')}` : null;
}

export function senderName(sender: string): string {
	const local = sender.split('@')[0] ?? sender;
	return local
		.split(/[._-]+/)
		.filter(Boolean)
		.map((part) => part[0].toUpperCase() + part.slice(1))
		.join(' ');
}

export function formatTime(iso: string, now = new Date()): string {
	const date = new Date(iso);
	const sameDay = date.toDateString() === now.toDateString();
	return sameDay
		? date.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })
		: date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}
