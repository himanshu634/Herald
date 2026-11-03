// Pure helpers for the setup editor. Limits match WorkspaceConfig on the server, so the editor
// blocks what the server would reject with a 422.
import type { Rule, RuleAction, Topic, WorkspaceConfig } from '#lib/api/client.js';
import type { Urgency } from '#lib/ui/tones.js';

export const SPAM_TOPIC = 'Spam or not for me';
export const MAX_TOPICS = 12;
export const MAX_TOPIC_LENGTH = 60;
export const MAX_MEANING_LENGTH = 120;
export const MAX_FACTS = 10;
export const MAX_FACT_LENGTH = 200;
export const MAX_GUIDANCE = 8;
export const MAX_GUIDANCE_LENGTH = 300;
export const MAX_RULES = 20;
export const MAX_DESCRIPTION = 2000;

/** Topics with one more, or the same list when it is empty, a repeat, spam or over the cap. */
export function addTopic(topics: Topic[], text: string): Topic[] {
	const name = text.trim().slice(0, MAX_TOPIC_LENGTH);
	const taken = [...topics.map((t) => t.name), SPAM_TOPIC].map((t) => t.toLowerCase());
	if (!name || taken.includes(name.toLowerCase()) || topics.length >= MAX_TOPICS) return topics;
	return [...topics, { name, meaning: null }];
}

/** A new, empty rule whose id is not taken. Verdicts are matched to rules by id. */
export function newRule(rules: Rule[]): Rule {
	const ids = new Set(rules.map((r) => r.id));
	let n = rules.length + 1;
	while (ids.has(`rule-${n}`)) n += 1;
	return { id: `rule-${n}`, name: '', when: '', action: 'alert', urgency: null };
}

/** Change a rule's action. Only set_urgency keeps an urgency; it starts at high. */
export function withAction(rule: Rule, action: RuleAction): Rule {
	if (action === 'set_urgency') return { ...rule, action, urgency: rule.urgency ?? 'high' };
	return { ...rule, action, urgency: null };
}

/**
 * A rule's "then" as one value for a single select: the action, or `set_urgency:<level>`.
 * Folding the urgency in means a set-urgency rule can never be saved without one.
 */
export function actionChoice(rule: Rule): string {
	return rule.action === 'set_urgency' ? `set_urgency:${rule.urgency ?? 'high'}` : rule.action;
}

/** The rule with the action (and urgency) picked in the select. */
export function withChoice(rule: Rule, choice: string): Rule {
	const [action, urgency] = choice.split(':') as [RuleAction, Urgency | undefined];
	const next = withAction(rule, action);
	return urgency ? { ...next, urgency } : next;
}

/** True when a list is close enough to its cap that the limit is worth showing. */
export function nearCap(count: number, max: number): boolean {
	return count >= max - 2;
}

/** Why the setup can't be saved yet, in the owner's words. Empty means it can. */
export function problems(config: WorkspaceConfig): string[] {
	const found: string[] = [];
	if (!config.business_profile.trim()) found.push('Describe your business.');
	if (!config.topics.length) found.push('Add at least one topic.');
	for (const topic of config.topics) {
		if ((topic.meaning?.length ?? 0) > MAX_MEANING_LENGTH)
			found.push(`${topic.name}'s meaning is too long.`);
	}
	if (config.facts?.some((f) => !f.trim())) found.push('Fill in or remove the empty fact.');
	if ((config.facts?.length ?? 0) > MAX_FACTS) found.push(`Keep to ${MAX_FACTS} facts.`);
	if (config.guidance?.some((g) => !g.trim()))
		found.push('Fill in or remove the empty guidance line.');
	for (const rule of config.rules ?? []) {
		const name = rule.name.trim() || 'A rule';
		if (!rule.name.trim()) found.push('Give every rule a name.');
		if (!rule.when.trim()) found.push(`${name} needs a "When".`);
		if (rule.action === 'set_urgency' && !rule.urgency) found.push(`${name} needs an urgency.`);
	}
	return [...new Set(found)];
}

/** True when the owner has changed the draft Herald gave them. */
export function isEdited(draft: WorkspaceConfig, current: WorkspaceConfig): boolean {
	return JSON.stringify(draft) !== JSON.stringify(current);
}
