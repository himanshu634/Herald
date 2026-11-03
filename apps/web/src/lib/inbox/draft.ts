// The question dialog's draft: the owner's unsaved fact and rule changes. Pure, so it is tested
// on its own. Nothing here saves; the dialog tries the draft on one email, then keeps it.
import type { EmailStatus, Rule, WorkspaceConfig } from '#lib/api/client.js';
import { STATUS } from '#lib/ui/tones.js';
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

/**
 * A fact's mark against the saved list, by text, not by place: removing a fact shifts the
 * ones after it, and they must not all read as changed.
 */
export function factMark(saved: string[], facts: string[], index: number): Mark {
	if (saved.includes(facts[index])) return null;
	return index < saved.length ? 'changed' : 'new';
}

/** The saved text a draft fact replaced, when that is clear: same count, old text gone. */
export function replacedFact(saved: string[], facts: string[], index: number): string | null {
	const before = saved[index];
	// After an add or a removal the places no longer line up, so it can't be told.
	if (before === undefined || facts.length !== saved.length) return null;
	return facts.includes(before) ? null : before;
}

/** Lines in `a` that `b` lacks, counting a repeated line once per copy. */
function missing(a: string[], b: string[]): number {
	const left = [...b];
	let count = 0;
	for (const line of a) {
		const at = left.indexOf(line);
		if (at === -1) count++;
		else left.splice(at, 1);
	}
	return count;
}

export type Outcome = { tone: 'success' | 'warning'; title: string; unsure: boolean };

/**
 * The trial's headline. A rule can move an email Herald is still unsure about, so "moved"
 * and "sure" are told apart; and no notes means the AI failed, which is never "sure".
 */
export function tryOutcome(
	now: EmailStatus,
	result: { status: EmailStatus; notes: { sure: boolean } | null }
): Outcome {
	const label = STATUS[result.status].label;
	if (!result.notes)
		return { tone: 'warning', title: 'Herald couldn’t read it with your changes', unsure: false };
	const unsure = !result.notes.sure;
	if (result.status !== now)
		return { tone: 'success', title: `With your changes, it goes to ${label}`, unsure };
	if (!unsure)
		return { tone: 'success', title: `Herald is sure now. It stays in ${label}`, unsure };
	return { tone: 'warning', title: `No change: still unsure, still in ${label}`, unsure };
}

export function ruleMark(saved: Rule[], rule: Rule): Mark {
	const before = saved.find((r) => r.id === rule.id);
	if (!before) return 'new';
	return JSON.stringify(before) === JSON.stringify(rule) ? null : 'changed';
}

/** How many facts and rules the draft changes, added or removed: the footer's count. */
export function countChanges(config: WorkspaceConfig, draft: Draft): number {
	const saved = draftOf(config);
	// An add, a change, a removal or a replace each count once, whatever their place.
	let count = Math.max(missing(draft.facts, saved.facts), missing(saved.facts, draft.facts));
	const ids = new Set([...saved.rules, ...draft.rules].map((r) => r.id));
	for (const id of ids) {
		const before = saved.rules.find((r) => r.id === id);
		const after = draft.rules.find((r) => r.id === id);
		if (JSON.stringify(before) !== JSON.stringify(after)) count++;
	}
	return count;
}
