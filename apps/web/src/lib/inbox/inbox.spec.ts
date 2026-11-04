import { describe, expect, it } from 'vitest';
import type { Email, WorkspaceConfig } from '#lib/api/client.js';
import {
	actionsFor,
	alertRuleSentence,
	alertsFor,
	countByView,
	deskQuestionsFor,
	firedAlertRules,
	nextAlert,
	floorLabel,
	highlight,
	questionActionsFor,
	questionsFor,
	senderName,
	tidyBody,
	visibleEmails,
	type Filters
} from './inbox';

const NO_FILTERS: Filters = { query: '', urgentOnly: false };

function email(id: string, over: Partial<Email> = {}): Email {
	return {
		id,
		workspace_id: 'w1',
		mailbox_id: null,
		sender: `${id}@customer.in`,
		reply_to: null,
		reply_address: `${id}@customer.in`,
		subject: `Subject ${id}`,
		body: 'Body',
		thread_id: null,
		status: 'inbox',
		notes: null,
		decision: null,
		context: null,
		in_spam: false,
		received_at: '2026-11-03T09:00:00Z',
		...over
	};
}

function notes(urgency: 'urgent' | 'high' | 'normal' | 'low', anger: number, sure = true) {
	return { topic: 'Orders and delivery', urgency, anger, summary: 's', quotes: [], sure };
}

describe('visibleEmails', () => {
	it('keeps alerts and needs-a-look in views of their own', () => {
		const list = [
			email('look', { status: 'needs_a_look' }),
			email('inbox'),
			email('alert', { status: 'alerted' })
		];
		expect(visibleEmails(list, 'alerts', NO_FILTERS).map((e) => e.id)).toEqual(['alert']);
		expect(visibleEmails(list, 'needs-a-look', NO_FILTERS).map((e) => e.id)).toEqual(['look']);
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

	it('filters by search text and leaves questions out of the table', () => {
		const list = [
			email('ritika', { subject: 'Flight on Thursday', notes: notes('urgent', 2) }),
			email('arjun', { subject: 'Refund', notes: notes('urgent', 4) }),
			email('sunita', { subject: 'Hindi', notes: notes('normal', 1, false) })
		];
		expect(visibleEmails(list, 'all', { ...NO_FILTERS, query: 'flight' }).map((e) => e.id)).toEqual(
			['ritika']
		);
		expect(visibleEmails(list, 'all', NO_FILTERS).map((e) => e.id)).toEqual(['arjun', 'ritika']);
	});
});

describe('questionsFor', () => {
	it('asks about unsure mail in any status decide sets, whatever the view', () => {
		const list = [
			email('closed', { status: 'closed', notes: notes('normal', 1, false) }),
			email('look', { status: 'needs_a_look', notes: notes('normal', 1, false) }),
			email('taken', { status: 'in_progress', notes: notes('normal', 1, false) }),
			email('finished', { status: 'done', notes: notes('normal', 1, false) }),
			email('sure', { status: 'needs_a_look', notes: notes('normal', 1) }),
			email('failed', { status: 'needs_a_look' })
		];
		expect(questionsFor(list).map((e) => e.id)).toEqual(['look', 'closed']);
	});
});

describe('alert desk', () => {
	const unsureAlert = email('unsure-alert', {
		status: 'alerted',
		notes: notes('urgent', 1, false)
	});
	const list = [
		email('high', { status: 'alerted', notes: notes('high', 5) }),
		email('urgent', { status: 'alerted', notes: notes('urgent', 2) }),
		unsureAlert,
		email('look', { status: 'needs_a_look', notes: notes('normal', 1, false) }),
		email('inbox', { notes: notes('urgent', 5) })
	];

	it('queues every alert in decide’s order, unsure ones too', () => {
		expect(alertsFor(list).map((e) => e.id)).toEqual(['urgent', 'unsure-alert', 'high']);
	});

	it('lists questions about mail that is not an alert, so none shows twice', () => {
		expect(questionsFor(list).map((e) => e.id)).toContain('unsure-alert');
		expect(deskQuestionsFor(list).map((e) => e.id)).toEqual(['look']);
	});

	it('opens the alert that moved into the place of the one that left', () => {
		const queue = alertsFor(list);
		expect(nextAlert(queue, 1)?.id).toBe('unsure-alert');
		expect(nextAlert(queue, 9)?.id).toBe('high');
		expect(nextAlert([], 0)).toBeNull();
	});

	it('says a rule the way the owner would', () => {
		expect(alertRuleSentence('The customer says they will post a review.')).toBe(
			'When the customer says they will post a review, alert me.'
		);
		expect(alertRuleSentence('VIP customer writes')).toBe('When VIP customer writes, alert me.');
	});

	it('finds the owner’s alert rules that matched, by id', () => {
		const config = {
			business_profile: 'Shoes',
			topics: [{ name: 'Orders', meaning: '' }],
			rules: [
				{ id: 'r1', name: 'Going public', when: 'they will post about us', action: 'alert' },
				{
					id: 'r2',
					name: 'Damaged',
					when: 'a pair arrived damaged',
					action: 'set_urgency',
					urgency: 'high'
				},
				{ id: 'r3', name: 'Other', when: 'something else', action: 'alert' }
			]
		} as WorkspaceConfig;
		const fired = email('a', {
			status: 'alerted',
			decision: {
				route: 'alert',
				urgency: 'urgent',
				reason: 'Rule: Going public',
				fired_rule_ids: ['r1', 'r2']
			}
		} as Partial<Email>);
		expect(firedAlertRules(fired, config).map((r) => r.id)).toEqual(['r1']);
	});
});

describe('countByView', () => {
	it('counts each email in its own view and in All mail', () => {
		const counts = countByView([
			email('a', { status: 'alerted' }),
			email('b', { status: 'closed' }),
			email('c')
		]);
		expect(counts).toMatchObject({ alerts: 1, 'needs-a-look': 0, closed: 1, inbox: 1, all: 3 });
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

describe('tidyBody', () => {
	it('caps blank-line runs and drops trailing spaces', () => {
		const body =
			'E-paper\r\r\n\r\r\n \r\r\n  Welcome! \r\n    \r\n\r\n  Good Morning!\r\r\n  Out now.\n';
		expect(tidyBody(body)).toBe('E-paper\n\n  Welcome!\n\n  Good Morning!\n  Out now.');
	});

	it('leaves a tidy body as it is', () => {
		const body = 'Hi,\n\nWhere is my order?';
		expect(tidyBody(tidyBody(body))).toBe(body);
	});
});

describe('questionActionsFor', () => {
	it('adds Done to every status, so a closed question clears without a correction', () => {
		expect(questionActionsFor('closed')).toEqual(['to-inbox', 'done']);
		expect(questionActionsFor('needs_a_look')).toEqual(['on-it', 'done']);
		expect(questionActionsFor('alerted')).toEqual(['on-it', 'not-urgent', 'done']);
	});
});
