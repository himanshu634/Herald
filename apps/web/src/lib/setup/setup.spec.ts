import { describe, expect, it } from 'vitest';
import type { Rule, Topic, WorkspaceConfig } from '#lib/api/client.js';
import {
	MAX_FACTS,
	MAX_MEANING_LENGTH,
	MAX_TOPICS,
	actionChoice,
	addTopic,
	isEdited,
	nearCap,
	newRule,
	problems,
	withAction,
	withChoice
} from './setup';

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

function topic(name: string, meaning: string | null = null): Topic {
	return { name, meaning };
}

function config(over: Partial<WorkspaceConfig> = {}): WorkspaceConfig {
	return {
		business_profile: 'We bake custom cakes to order in Ahmedabad.',
		topics: [topic('Orders and delivery')],
		facts: [],
		important_contacts: [],
		guidance: [],
		rules: [],
		...over
	};
}

describe('addTopic', () => {
	it('adds a trimmed topic without a meaning', () => {
		expect(addTopic([topic('Orders')], '  Allergies ')).toEqual([
			topic('Orders'),
			{ name: 'Allergies', meaning: null }
		]);
	});

	it('ignores blanks, repeats and the spam topic', () => {
		expect(addTopic([topic('Orders')], '   ')).toEqual([topic('Orders')]);
		expect(addTopic([topic('Orders')], ' orders ')).toEqual([topic('Orders')]);
		expect(addTopic([topic('Orders')], 'spam or not for me')).toEqual([topic('Orders')]);
	});

	it('stops at the cap', () => {
		const full = Array.from({ length: MAX_TOPICS }, (_, i) => topic(`Topic ${i}`));
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

describe('actionChoice and withChoice', () => {
	it('folds the urgency into a set_urgency choice', () => {
		expect(actionChoice(rule())).toBe('alert');
		expect(actionChoice(rule({ action: 'set_urgency', urgency: 'low' }))).toBe('set_urgency:low');
	});

	it('sets the action and urgency from one choice', () => {
		const set = withChoice(rule(), 'set_urgency:urgent');
		expect(set).toMatchObject({ action: 'set_urgency', urgency: 'urgent' });
		expect(withChoice(set, 'close')).toMatchObject({ action: 'close', urgency: null });
	});
});

describe('nearCap', () => {
	it('shows the limit only in the last two places', () => {
		expect(nearCap(7, MAX_FACTS)).toBe(false);
		expect(nearCap(8, MAX_FACTS)).toBe(true);
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
				facts: [' '],
				guidance: [' '],
				rules: [rule({ when: '' }), rule({ name: '', action: 'set_urgency', urgency: null })]
			})
		);
		expect(found).toEqual([
			'Add at least one topic.',
			'Fill in or remove the empty fact.',
			'Fill in or remove the empty guidance line.',
			'Event cake at risk needs a "When".',
			'Give every rule a name.',
			'A rule needs an urgency.'
		]);
	});
});

describe('problems for facts and meanings', () => {
	it('caps facts', () => {
		const facts = Array.from({ length: MAX_FACTS + 1 }, (_, i) => `Fact ${i}`);
		expect(problems(config({ facts }))).toEqual(['Keep to 10 facts.']);
	});

	it('names a topic whose meaning is too long', () => {
		const long = 'x'.repeat(MAX_MEANING_LENGTH + 1);
		expect(problems(config({ topics: [topic('Orders', long)] }))).toEqual([
			"Orders's meaning is too long."
		]);
		expect(problems(config({ topics: [topic('Orders', 'x'.repeat(MAX_MEANING_LENGTH))] }))).toEqual(
			[]
		);
	});
});

describe('isEdited', () => {
	it('notices a change', () => {
		const draft = config();
		expect(isEdited(draft, config())).toBe(false);
		expect(isEdited(draft, config({ topics: [topic('Orders')] }))).toBe(true);
		expect(isEdited(draft, config({ topics: [topic('Orders and delivery', 'Where is it')] }))).toBe(
			true
		);
		expect(isEdited(draft, config({ facts: ['Returns within 7 days.'] }))).toBe(true);
	});
});
