import { describe, expect, it } from 'vitest';
import type { Email } from '#lib/api/client.js';
import {
	actionsFor,
	countByView,
	floorLabel,
	highlight,
	senderName,
	visibleEmails,
	type Filters
} from './inbox';

const NO_FILTERS: Filters = { query: '', urgentOnly: false, angry: false, unsure: false };

function email(id: string, over: Partial<Email> = {}): Email {
	return {
		id,
		workspace_id: 'w1',
		sender: `${id}@customer.in`,
		subject: `Subject ${id}`,
		body: 'Body',
		thread_id: null,
		status: 'inbox',
		notes: null,
		decision: null,
		context: null,
		received_at: '2026-11-03T09:00:00Z',
		...over
	};
}

function notes(urgency: 'urgent' | 'high' | 'normal' | 'low', anger: number, sure = true) {
	return { topic: 'Orders and delivery', urgency, anger, summary: 's', quotes: [], sure };
}

describe('visibleEmails', () => {
	it('shows alerted and needs-a-look under Needs you, alerted first', () => {
		const list = [
			email('look', { status: 'needs_a_look' }),
			email('inbox'),
			email('alert', { status: 'alerted' })
		];
		expect(visibleEmails(list, 'needs-you', NO_FILTERS).map((e) => e.id)).toEqual([
			'alert',
			'look'
		]);
	});

	it('sorts by urgency, then anger, then newest first', () => {
		const list = [
			email('normal-calm', { notes: notes('normal', 1) }),
			email('high-angry', { notes: notes('high', 4) }),
			email('high-calm-new', { notes: notes('high', 1), received_at: '2026-11-03T10:00:00Z' }),
			email('high-calm-old', { notes: notes('high', 1), received_at: '2026-11-03T08:00:00Z' })
		];
		expect(visibleEmails(list, 'inbox', NO_FILTERS).map((e) => e.id)).toEqual([
			'high-angry',
			'high-calm-new',
			'high-calm-old',
			'normal-calm'
		]);
	});

	it('filters by search text, anger and unsure notes', () => {
		const list = [
			email('ritika', { subject: 'Flight on Thursday', notes: notes('urgent', 2) }),
			email('arjun', { subject: 'Refund', notes: notes('urgent', 4) }),
			email('sunita', { subject: 'Hindi', notes: notes('normal', 1, false) })
		];
		expect(visibleEmails(list, 'all', { ...NO_FILTERS, query: 'flight' }).map((e) => e.id)).toEqual(
			['ritika']
		);
		expect(visibleEmails(list, 'all', { ...NO_FILTERS, angry: true }).map((e) => e.id)).toEqual([
			'arjun'
		]);
		expect(visibleEmails(list, 'all', { ...NO_FILTERS, unsure: true }).map((e) => e.id)).toEqual([
			'sunita'
		]);
	});
});

describe('countByView', () => {
	it('counts each email in its own view and in All mail', () => {
		const counts = countByView([
			email('a', { status: 'alerted' }),
			email('b', { status: 'closed' }),
			email('c')
		]);
		expect(counts).toMatchObject({ 'needs-you': 1, closed: 1, inbox: 1, all: 3 });
	});
});

describe('actionsFor', () => {
	it('offers Not urgent only on alerted emails, as the API allows', () => {
		expect(actionsFor('alerted')).toEqual(['on-it', 'not-urgent']);
		expect(actionsFor('inbox')).not.toContain('not-urgent');
		expect(actionsFor('in_progress')).toEqual(['done']);
	});

	it('offers Move to Inbox only on closed emails, as the API allows', () => {
		expect(actionsFor('closed')).toEqual(['to-inbox']);
		expect(actionsFor('inbox')).not.toContain('to-inbox');
		expect(actionsFor('alerted')).not.toContain('to-inbox');
	});
});

describe('highlight', () => {
	it('marks the quoted lines and keeps the rest', () => {
		const body = 'Hi. I fly on Thursday. Thanks.';
		expect(highlight(body, ['I fly on Thursday.'])).toEqual([
			{ text: 'Hi. ', quoted: false },
			{ text: 'I fly on Thursday.', quoted: true },
			{ text: ' Thanks.', quoted: false }
		]);
	});

	it('ignores quotes that are not in the body and merges overlaps', () => {
		const body = 'abcdef';
		expect(highlight(body, ['zzz', 'bcd', 'cde'])).toEqual([
			{ text: 'a', quoted: false },
			{ text: 'bcd', quoted: true },
			{ text: 'e', quoted: true },
			{ text: 'f', quoted: false }
		]);
	});
});

describe('labels', () => {
	it('names floor flags in plain words', () => {
		expect(floorLabel(['legal_threat'])).toBe('Safety floor: legal threat');
		expect(floorLabel(['about_to_cancel'])).toBeNull();
	});

	it('turns an address into a name', () => {
		expect(senderName('ritika.sharma@gmail.com')).toBe('Ritika Sharma');
	});
});
