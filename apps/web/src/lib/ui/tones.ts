// How Herald's data maps onto the design system's tones and labels.
// One place, so a status never shows two colours or two names. Rules: docs/design-system.md.
import type { EmailStatus } from '#lib/api/client.js';

export type Tone = 'danger' | 'warning' | 'success' | 'neutral' | 'muted' | 'floor' | 'accent';

export type Urgency = 'urgent' | 'high' | 'normal' | 'low';

export const STATUS: Record<EmailStatus, { label: string; tone: Tone }> = {
	new: { label: 'Reading', tone: 'muted' },
	alerted: { label: 'Needs you now', tone: 'danger' },
	needs_a_look: { label: 'Needs a look', tone: 'warning' },
	inbox: { label: 'Inbox', tone: 'neutral' },
	in_progress: { label: 'In progress', tone: 'success' },
	done: { label: 'Done', tone: 'muted' },
	closed: { label: 'Closed quietly', tone: 'muted' }
};

export const URGENCY: Record<Urgency, { label: string; tone: Tone }> = {
	urgent: { label: 'Urgent', tone: 'danger' },
	high: { label: 'High', tone: 'warning' },
	normal: { label: 'Normal', tone: 'neutral' },
	low: { label: 'Low', tone: 'muted' }
};

export const ANGER_LABELS = [
	'Calm',
	'Mildly frustrated',
	'Frustrated',
	'Angry',
	'Extremely angry'
] as const;

/** "Anger 4 of 5, angry". The anger meter's accessible name; colour alone never carries it. */
export function angerLabel(level: number): string {
	const clamped = Math.min(5, Math.max(1, Math.round(level)));
	return `Anger ${clamped} of 5, ${ANGER_LABELS[clamped - 1].toLowerCase()}`;
}
