// The question dialog's draft: the owner's unsaved fact and rule changes. Pure, so it is tested
// on its own. Nothing here saves; the dialog tries the draft on one email, then keeps it.
import type { Rule, WorkspaceConfig } from '#lib/api/client.js';
import { MAX_FACTS } from './inbox';

export type Draft = { facts: string[]; rules: Rule[] };

/** What the side panel has open: a fact or rule by place, or null for a new one. */
export type Edit = { kind: 'fact'; index: number | null } | { kind: 'rule'; id: string | null };

export type Mark = 'new' | 'changed' | null;

export function draftOf(config: WorkspaceConfig): Draft {
	return { facts: [...(config.facts ?? [])], rules: (config.rules ?? []).map((r) => ({ ...r })) };
}

/** The saved config with the draft's facts and rules: what a try or a keep sends. */
export function withDraft(config: WorkspaceConfig, draft: Draft): WorkspaceConfig {
	return { ...config, facts: draft.facts, rules: draft.rules };
}

/**
 * The facts with one put in place: `index` changes that fact, null adds one. Empty text
 * removes it. At the cap a new fact goes in place of `replace`, so the save is never refused.
 */
export function putFact(
	facts: string[],
	index: number | null,
	text: string,
	replace: number | null = null
): string[] {
	const line = text.trim();
	const at = index ?? (facts.length >= MAX_FACTS ? replace : null);
	if (at === null) return line ? [...facts, line] : facts;
	if (!line) return facts.filter((_, i) => i !== at);
	return facts.map((fact, i) => (i === at ? line : fact));
}

/** The rules with this one in place: same id replaces it, a new id adds it at the end. */
export function putRule(rules: Rule[], rule: Rule): Rule[] {
	const clean = { ...rule, name: rule.name.trim(), when: rule.when.trim() };
	return rules.some((r) => r.id === rule.id)
		? rules.map((r) => (r.id === rule.id ? clean : r))
		: [...rules, clean];
}

/** Why the side panel can't keep this rule yet, in the owner's words. Null means it can. */
export function ruleProblem(rule: Rule): string | null {
	if (!rule.name.trim()) return 'Give the rule a name.';
	if (!rule.when.trim()) return 'Say when the rule applies.';
	if (rule.action === 'set_urgency' && !rule.urgency) return 'Pick an urgency.';
	return null;
}

/** A fact's mark against the saved list, by place. Removing a fact shifts the ones after it. */
export function factMark(saved: string[], facts: string[], index: number): Mark {
	if (index >= saved.length) return 'new';
	return facts[index] === saved[index] ? null : 'changed';
}

export function ruleMark(saved: Rule[], rule: Rule): Mark {
	const before = saved.find((r) => r.id === rule.id);
	if (!before) return 'new';
	return JSON.stringify(before) === JSON.stringify(rule) ? null : 'changed';
}

/** How many facts and rules the draft changes, added or removed: the footer's count. */
export function countChanges(config: WorkspaceConfig, draft: Draft): number {
	const saved = draftOf(config);
	let count = 0;
	const longest = Math.max(saved.facts.length, draft.facts.length);
	for (let i = 0; i < longest; i++) if (saved.facts[i] !== draft.facts[i]) count++;
	const ids = new Set([...saved.rules, ...draft.rules].map((r) => r.id));
	for (const id of ids) {
		const before = saved.rules.find((r) => r.id === id);
		const after = draft.rules.find((r) => r.id === id);
		if (JSON.stringify(before) !== JSON.stringify(after)) count++;
	}
	return count;
}
