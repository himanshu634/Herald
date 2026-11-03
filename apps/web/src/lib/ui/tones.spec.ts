import { describe, expect, it } from 'vitest';
import { STATUS, URGENCY, angerLabel } from './tones';

describe('tones', () => {
	it('never uses the accent tone for a status or urgency', () => {
		const tones = [...Object.values(STATUS), ...Object.values(URGENCY)].map((t) => t.tone);
		expect(tones).not.toContain('accent');
	});

	it('names the owner-facing statuses the way the docs do', () => {
		expect(STATUS.alerted.label).toBe('Needs you now');
		expect(STATUS.needs_a_look.label).toBe('Needs a look');
		expect(STATUS.closed.label).toBe('Closed quietly');
	});

	it('labels anger with the number and the word', () => {
		expect(angerLabel(4)).toBe('Anger 4 of 5, angry');
		expect(angerLabel(1)).toBe('Anger 1 of 5, calm');
	});

	it('clamps anger to the 1 to 5 scale', () => {
		expect(angerLabel(0)).toBe('Anger 1 of 5, calm');
		expect(angerLabel(9)).toBe('Anger 5 of 5, extremely angry');
	});
});
