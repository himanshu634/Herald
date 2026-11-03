<script lang="ts">
	import { tick } from 'svelte';
	import type { WorkspaceConfig } from '#lib/api/client.js';
	import { Button, Icon, Panel, URGENCY, type Urgency } from '#lib/ui/index.js';
	import {
		ACTIONS,
		MAX_FACT_LENGTH,
		MAX_FACTS,
		MAX_GUIDANCE,
		MAX_GUIDANCE_LENGTH,
		MAX_MEANING_LENGTH,
		MAX_RULES,
		MAX_TOPIC_LENGTH,
		MAX_TOPICS,
		SPAM_TOPIC,
		addTopic,
		newRule,
		withAction
	} from './setup';

	// Edits a WorkspaceConfig in place. Used by onboarding; a settings page can reuse it.
	let { config = $bindable() }: { config: WorkspaceConfig } = $props();

	let topicText = $state('');
	let editor = $state<HTMLElement>();

	const facts = $derived(config.facts ?? []);
	const guidance = $derived(config.guidance ?? []);
	const rules = $derived(config.rules ?? []);

	function onTopicKey(event: KeyboardEvent) {
		if (event.key !== 'Enter') return;
		event.preventDefault();
		submitTopic();
	}

	function submitTopic() {
		config.topics = addTopic(config.topics, topicText);
		topicText = '';
	}

	// New lines and rules start empty, so move focus into them.
	async function focusLast(selector: string) {
		await tick();
		const fields = editor?.querySelectorAll<HTMLElement>(selector);
		fields?.[fields.length - 1]?.focus();
	}

	function addLine() {
		config.guidance = [...guidance, ''];
		focusLast('[data-guidance]');
	}

	function addFact() {
		config.facts = [...facts, ''];
		focusLast('[data-fact]');
	}

	function addRule() {
		config.rules = [...rules, newRule(rules)];
		focusLast('[data-rule-name]');
	}
</script>

{#snippet count(n: number, max: number)}
	<span class="rounded-xs bg-subtle px-1.5 text-xs font-bold text-muted">{n} of {max}</span>
{/snippet}

<div bind:this={editor} class="flex flex-col gap-4">
	<Panel title="Topics">
		{#snippet actions()}{@render count(config.topics.length, MAX_TOPICS)}{/snippet}
		<p class="mb-3 text-sm text-muted">Herald files every email under one of these.</p>
		<ul aria-label="Topics">
			{#each config.topics as topic, i (topic.name)}
				<li
					class="flex items-center gap-2 border-t border-dashed border-line-dashed py-2 first:border-t-0"
				>
					<span class="w-48 flex-none truncate text-sm font-semibold">{topic.name}</span>
					<label class="sr-only" for={`topic-meaning-${i}`}>What {topic.name} covers</label>
					<input
						id={`topic-meaning-${i}`}
						bind:value={config.topics[i].meaning}
						maxlength={MAX_MEANING_LENGTH}
						placeholder="What belongs here, in one line"
						class="h-control-md min-w-0 flex-1 rounded-sm border border-transparent px-2 text-md hover:border-line focus:border-control"
					/>
					<button
						type="button"
						aria-label={`Remove ${topic.name}`}
						class="flex size-control-md flex-none cursor-pointer items-center justify-center rounded-sm text-muted hover:bg-subtle"
						onclick={() => (config.topics = config.topics.filter((_, j) => j !== i))}
						><Icon name="close" size={16} /></button
					>
				</li>
			{/each}
			<li
				class="flex items-center gap-2 border-t border-dashed border-line-dashed py-2 text-sm font-semibold text-muted"
				title="Every email can go here. It can't be removed."
			>
				<span class="w-48 flex-none truncate">{SPAM_TOPIC}</span>
			</li>
		</ul>
		{#if config.topics.length < MAX_TOPICS}
			<div class="mt-3 flex items-center gap-2">
				<label class="sr-only" for="new-topic">New topic</label>
				<input
					id="new-topic"
					bind:value={topicText}
					onkeydown={onTopicKey}
					maxlength={MAX_TOPIC_LENGTH}
					placeholder="Add a topic, like Custom designs"
					class="h-control-md w-72 rounded-sm border border-control bg-surface px-2.5 text-sm"
				/>
				<Button size="sm" onclick={submitTopic} disabled={!topicText.trim()}>
					<Icon name="plus" size={14} />Add topic
				</Button>
			</div>
		{/if}
		{#if !config.topics.length}
			<p class="mt-2 text-sm font-semibold text-danger-fg">Add at least one topic.</p>
		{/if}
	</Panel>

	<Panel title="Facts">
		{#snippet actions()}{@render count(facts.length, MAX_FACTS)}{/snippet}
		<p class="mb-1 text-sm text-muted">
			What is true about your business, like your return window or delivery times. Herald checks
			emails against these.
		</p>
		{#if !facts.length}
			<p
				class="my-2 rounded-md border border-dashed border-line-strong bg-sunken p-3 text-sm text-muted"
			>
				No facts yet. Add one such as "Returns are accepted within 7 days of delivery."
			</p>
		{/if}
		<ul>
			<!-- Facts can be empty or repeat while the owner types, so the index is the key. -->
			{#each facts as fact, i (i)}
				<li
					class="flex items-center gap-2 border-t border-dashed border-line-dashed py-2 first:border-t-0"
				>
					<label class="sr-only" for={`fact-${i}`}>Fact {i + 1}</label>
					<input
						id={`fact-${i}`}
						data-fact
						bind:value={config.facts![i]}
						maxlength={MAX_FACT_LENGTH}
						class="h-control-md min-w-0 flex-1 rounded-sm border border-transparent px-2 text-md hover:border-line focus:border-control"
					/>
					<button
						type="button"
						aria-label={`Remove fact ${i + 1}${fact ? `, ${fact}` : ''}`}
						class="flex size-control-md flex-none cursor-pointer items-center justify-center rounded-sm text-muted hover:bg-subtle"
						onclick={() => (config.facts = facts.filter((_, j) => j !== i))}
						><Icon name="close" size={16} /></button
					>
				</li>
			{/each}
		</ul>
		{#if facts.length < MAX_FACTS}
			<Button variant="quiet" size="sm" onclick={addFact}
				><Icon name="plus" size={14} />Add a fact</Button
			>
		{/if}
	</Panel>

	<Panel title="Guidance">
		{#snippet actions()}{@render count(guidance.length, MAX_GUIDANCE)}{/snippet}
		<p class="mb-1 text-sm text-muted">
			How your business judges urgency. Facts go above; these lines say what matters most.
		</p>
		{#if !guidance.length}
			<p
				class="my-2 rounded-md border border-dashed border-line-strong bg-sunken p-3 text-sm text-muted"
			>
				No guidance yet. Add a line such as "Wedding planners are always important."
			</p>
		{/if}
		<ul>
			<!-- Lines can be empty or repeat while the owner types, so the index is the key. -->
			{#each guidance as line, i (i)}
				<li
					class="flex items-center gap-2 border-t border-dashed border-line-dashed py-2 first:border-t-0"
				>
					<label class="sr-only" for={`guidance-${i}`}>Guidance line {i + 1}</label>
					<input
						id={`guidance-${i}`}
						data-guidance
						bind:value={config.guidance![i]}
						maxlength={MAX_GUIDANCE_LENGTH}
						class="h-control-md min-w-0 flex-1 rounded-sm border border-transparent px-2 text-md hover:border-line focus:border-control"
					/>
					<button
						type="button"
						aria-label={`Remove guidance line ${i + 1}${line ? `, ${line}` : ''}`}
						class="flex size-control-md flex-none cursor-pointer items-center justify-center rounded-sm text-muted hover:bg-subtle"
						onclick={() => (config.guidance = guidance.filter((_, j) => j !== i))}
						><Icon name="close" size={16} /></button
					>
				</li>
			{/each}
		</ul>
		{#if guidance.length < MAX_GUIDANCE}
			<Button variant="quiet" size="sm" onclick={addLine}
				><Icon name="plus" size={14} />Add a line</Button
			>
		{/if}
	</Panel>

	<Panel title="Rules">
		{#snippet actions()}{@render count(rules.length, MAX_RULES)}{/snippet}
		<p class="mb-3 text-sm text-muted">
			What happens when an email matches. Safety, hacked accounts and legal threats always alert
			you, whatever your rules say.
		</p>
		{#if !rules.length}
			<p
				class="mb-3 rounded-md border border-dashed border-line-strong bg-sunken p-3 text-sm text-muted"
			>
				No rules yet. Herald still alerts you for urgent emails and very angry customers.
			</p>
		{/if}
		<ul class="flex flex-col gap-2.5">
			{#each rules as rule, i (rule.id)}
				<li class="flex flex-col gap-2.5 rounded-md border border-line p-3">
					<div class="flex items-center gap-2">
						<label class="sr-only" for={`rule-name-${rule.id}`}>Rule name</label>
						<input
							id={`rule-name-${rule.id}`}
							data-rule-name
							bind:value={config.rules![i].name}
							placeholder="Name this rule"
							class="h-control-md min-w-0 flex-1 rounded-sm border border-transparent px-2 text-md font-bold hover:border-line focus:border-control"
						/>
						<button
							type="button"
							aria-label={`Remove ${rule.name || 'this rule'}`}
							class="flex size-control-md flex-none cursor-pointer items-center justify-center rounded-sm text-muted hover:bg-subtle"
							onclick={() => (config.rules = rules.filter((r) => r.id !== rule.id))}
							><Icon name="close" size={16} /></button
						>
					</div>
					<div class="flex flex-col gap-1 px-2">
						<label class="text-xs font-bold text-muted" for={`rule-when-${rule.id}`}>When</label>
						<textarea
							id={`rule-when-${rule.id}`}
							bind:value={config.rules![i].when}
							rows="2"
							placeholder="The customer says the cake arrived damaged"
							class="resize-y rounded-sm border border-control bg-surface px-2.5 py-1.5 text-md"
						></textarea>
					</div>
					<div class="flex flex-wrap items-center gap-2 px-2">
						<span class="w-10 text-xs font-bold text-muted" id={`rule-then-${rule.id}`}>Then</span>
						<div
							role="group"
							aria-labelledby={`rule-then-${rule.id}`}
							class="inline-flex overflow-hidden rounded-sm border border-control"
						>
							{#each ACTIONS as action (action.id)}
								{@const on = rule.action === action.id}
								<button
									type="button"
									aria-pressed={on}
									class={[
										'inline-flex h-control-md cursor-pointer items-center gap-1 border-l border-line-dashed px-2.5 text-sm first:border-l-0',
										on
											? 'bg-accent-tint font-bold text-ink ring-2 ring-ink ring-inset'
											: 'bg-surface font-semibold text-neutral-fg'
									]}
									onclick={() => (config.rules![i] = withAction(rule, action.id))}
								>
									{#if on}<Icon name="check" size={14} />{/if}{action.label}
								</button>
							{/each}
						</div>
						{#if rule.action === 'set_urgency'}
							<label class="flex items-center gap-1.5 text-sm">
								<span class="text-xs font-bold text-muted">to</span>
								<select
									bind:value={config.rules![i].urgency}
									class="h-control-md rounded-sm border border-control bg-surface px-2 text-sm"
								>
									{#each Object.entries(URGENCY) as [value, { label }] (value)}
										<option value={value as Urgency}>{label}</option>
									{/each}
								</select>
							</label>
						{/if}
					</div>
				</li>
			{/each}
		</ul>
		{#if rules.length < MAX_RULES}
			<Button variant="quiet" size="sm" class="mt-2" onclick={addRule}>
				<Icon name="plus" size={14} />Add a rule
			</Button>
		{/if}
	</Panel>
</div>
