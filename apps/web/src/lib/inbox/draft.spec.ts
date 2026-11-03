import { describe, expect, it } from 'vitest';
import type { Rule, WorkspaceConfig } from '#lib/api/client.js';
import {
	countChanges,
	draftOf,
	factMark,
	putFact,
	putRule,
	ruleMark,
	ruleProblem,
	withDraft
} from './draft';

function rule(over: Partial<Rule> = {}): Rule {
	return { id: 'r1', name: 'Stockist', when: 'A stockist writes', action: 'alert', ...over };
}

function config(over: Partial<WorkspaceConfig> = {}): WorkspaceConfig {
	return {
		business_profile: 'Shoes',
		topics: [{ name: 'Orders', meaning: null }],
		facts: ['a', 'b'],
		rules: [rule()],
		...over
	};
}

const TEN = Array.from({ length: 10 }, (_, i) => `fact ${i + 1}`);

describe('putFact', () => {
	it('adds, changes and removes by place', () => {
		expect(putFact(['a'], null, ' b ')).toEqual(['a', 'b']);
		expect(putFact(['a', 'b'], 1, 'c')).toEqual(['a', 'c']);
		expect(putFact(['a', 'b'], 0, '  ')).toEqual(['b']);
		expect(putFact(['a'], null, '')).toEqual(['a']);
	});

	it('puts a new fact in place of the picked one at the cap', () => {
		expect(putFact(TEN, null, 'new', 2)[2]).toBe('new');
		expect(putFact(TEN, null, 'new', 2)).toHaveLength(10);
	});
});

describe('putRule', () => {
	it('replaces by id and adds a new id at the end', () => {
		expect(putRule([rule()], rule({ name: ' New name ' }))).toEqual([rule({ name: 'New name' })]);
		expect(putRule([rule()], rule({ id: 'r2' })).map((r) => r.id)).toEqual(['r1', 'r2']);
	});
});

describe('ruleProblem', () => {
	it('needs a name, a When and an urgency for set urgency', () => {
		expect(ruleProblem(rule())).toBeNull();
		expect(ruleProblem(rule({ name: ' ' }))).toBe('Give the rule a name.');
		expect(ruleProblem(rule({ when: '' }))).toBe('Say when the rule applies.');
		expect(ruleProblem(rule({ action: 'set_urgency', urgency: null }))).toBe('Pick an urgency.');
	});
});

describe('marks and counts', () => {
	it('marks new and changed facts and rules', () => {
		expect(factMark(['a', 'b'], ['a', 'x', 'y'], 0)).toBeNull();
		expect(factMark(['a', 'b'], ['a', 'x', 'y'], 1)).toBe('changed');
		expect(factMark(['a', 'b'], ['a', 'x', 'y'], 2)).toBe('new');
		expect(ruleMark([rule()], rule())).toBeNull();
		expect(ruleMark([rule()], rule({ when: 'other' }))).toBe('changed');
		expect(ruleMark([rule()], rule({ id: 'r2' }))).toBe('new');
	});

	it('counts each changed, added or removed fact and rule', () => {
		const saved = config();
		expect(countChanges(saved, draftOf(saved))).toBe(0);
		const draft = { facts: ['a', 'c', 'd'], rules: [rule({ id: 'r2' })] };
		// Fact 2 changed, fact 3 added, rule r1 removed, rule r2 added.
		expect(countChanges(saved, draft)).toBe(4);
	});

	it('draftOf copies, so editing the draft leaves the saved config alone', () => {
		const saved = config();
		const draft = draftOf(saved);
		draft.facts.push('z');
		draft.rules[0].name = 'Changed';
		expect(saved.facts).toEqual(['a', 'b']);
		expect(saved.rules?.[0].name).toBe('Stockist');
		expect(withDraft(saved, draft).facts).toEqual(['a', 'b', 'z']);
	});
});
