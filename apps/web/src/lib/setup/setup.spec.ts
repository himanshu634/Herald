import { describe, expect, it } from 'vitest';
import type { Rule, WorkspaceConfig } from '#lib/api/client.js';
import { MAX_TOPICS, addTopic, isEdited, newRule, problems, withAction } from './setup';

function rule(over: Partial<Rule> = {}): Rule {
	return {
		id: 'event-cake',
		name: 'Event cake at risk',
		when: 'The order is for today or tomorrow and something is wrong',
		action: 'alert',
		urgency: null,
		...over
	};
}

function config(over: Partial<WorkspaceConfig> = {}): WorkspaceConfig {
	return {
		business_profile: 'We bake custom cakes to order in Ahmedabad.',
		topics: ['Orders and delivery'],
		important_contacts: [],
		guidance: [],
		rules: [],
		...over
	};
}

describe('addTopic', () => {
	it('adds a trimmed topic', () => {
		expect(addTopic(['Orders'], '  Allergies ')).toEqual(['Orders', 'Allergies']);
	});

	it('ignores blanks, repeats and the spam topic', () => {
		expect(addTopic(['Orders'], '   ')).toEqual(['Orders']);
		expect(addTopic(['Orders'], 'orders')).toEqual(['Orders']);
		expect(addTopic(['Orders'], 'spam or not for me')).toEqual(['Orders']);
	});

	it('stops at the cap', () => {
		const full = Array.from({ length: MAX_TOPICS }, (_, i) => `Topic ${i}`);
		expect(addTopic(full, 'One more')).toBe(full);
	});
});

describe('newRule', () => {
	it('picks an id no other rule has', () => {
		const rules = [rule({ id: 'rule-2' }), rule({ id: 'rule-3' })];
		expect(newRule(rules).id).toBe('rule-4');
		expect(newRule([rule({ id: 'rule-1' })]).id).toBe('rule-2');
	});
});

describe('withAction', () => {
	it('gives set urgency a starting urgency and clears it otherwise', () => {
		const set = withAction(rule(), 'set_urgency');
		expect(set.urgency).toBe('high');
		expect(withAction(set, 'close').urgency).toBeNull();
	});

	it('keeps an urgency the owner already chose', () => {
		expect(withAction(rule({ urgency: 'urgent' }), 'set_urgency').urgency).toBe('urgent');
	});
});

describe('problems', () => {
	it('is empty for a setup the server accepts', () => {
		expect(problems(config({ rules: [rule()] }))).toEqual([]);
	});

	it('names what blocks saving', () => {
		const found = problems(
			config({
				topics: [],
				guidance: [' '],
				rules: [rule({ when: '' }), rule({ name: '', action: 'set_urgency', urgency: null })]
			})
		);
		expect(found).toEqual([
			'Add at least one topic.',
			'Fill in or remove the empty guidance line.',
			'Event cake at risk needs a "When".',
			'Give every rule a name.',
			'A rule needs an urgency.'
		]);
	});
});

describe('isEdited', () => {
	it('notices a change', () => {
		const draft = config();
		expect(isEdited(draft, config())).toBe(false);
		expect(isEdited(draft, config({ topics: ['Orders'] }))).toBe(true);
	});
});
