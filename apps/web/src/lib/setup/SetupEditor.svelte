<script lang="ts">
	import { tick } from 'svelte';
	import type { WorkspaceConfig } from '#lib/api/client.js';
	import { Button, Icon, Panel, TONE_CLASSES, URGENCY, type Tone } from '#lib/ui/index.js';
	import {
		MAX_FACT_LENGTH,
		MAX_FACTS,
		MAX_GUIDANCE,
		MAX_GUIDANCE_LENGTH,
		MAX_MEANING_LENGTH,
		MAX_RULES,
		MAX_TOPIC_LENGTH,
		MAX_TOPICS,
		SPAM_TOPIC,
		actionChoice,
		addTopic,
		nearCap,
		newRule,
		withChoice
	} from './setup';

	// Edits a WorkspaceConfig in place. Used by onboarding; a settings page can reuse it.
	let { config = $bindable() }: { config: WorkspaceConfig } = $props();

	type LineList = 'facts' | 'guidance';

	let topicText = $state('');
	let editor = $state<HTMLElement>();

	const facts = $derived(config.facts ?? []);
	const guidance = $derived(config.guidance ?? []);
	const rules = $derived(config.rules ?? []);

	// The action select is tinted like the status it leads to, so "Alert me" reads red at a glance.
	const ACTION_TONE: Record<string, Tone> = {
		alert: 'danger',
		set_urgency: 'warning',
		close: 'neutral'
	};

	// A blank field shows its border, so a new, empty line is never invisible.
	const lineField =
		'min-w-0 flex-1 resize-none rounded-sm border px-2 py-1.5 text-md leading-snug field-sizing-content focus:border-control';
	const blankOr = (value: string) =>
		value.trim() ? 'border-transparent hover:border-line' : 'border-control';
	const addButton =
		'inline-flex h-control-md cursor-pointer items-center gap-1.5 self-start px-2 text-sm font-bold text-neutral-fg hover:text-ink';
	const removeButton =
		'flex size-control-md flex-none cursor-pointer items-center justify-center rounded-sm text-muted hover:bg-subtle';

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

	function addLine(list: LineList) {
		config[list] = [...(config[list] ?? []), ''];
		focusLast(`[data-line="${list}"]`);
	}

	function setLine(list: LineList, i: number, value: string) {
		config[list] = (config[list] ?? []).map((line, j) => (j === i ? value : line));
	}

	function removeLine(list: LineList, i: number) {
		config[list] = (config[list] ?? []).filter((_, j) => j !== i);
	}

	function addRule() {
		config.rules = [...rules, newRule(rules)];
		focusLast('[data-rule-when]');
	}
</script>

{#snippet cap(n: number, max: number)}
	{#if nearCap(n, max)}
		<span class="rounded-xs bg-warning-bg px-1.5 text-xs font-bold text-warning-fg"
			>{n} of {max}</span
		>
	{/if}
{/snippet}

{#snippet help(text: string)}
	<span class="hidden text-right text-sm text-muted sm:inline">{text}</span>
{/snippet}

{#snippet lines(
	list: LineList,
	items: string[],
	opts: { noun: string; max: number; maxLength: number; example: string; add: string }
)}
	{#if !items.length}
		<p class="px-2 pb-1 text-sm text-muted">None yet. For example: {opts.example}</p>
	{/if}
	<ul>
		<!-- Lines can be empty or repeat while the owner types, so the index is the key. -->
		{#each items as line, i (i)}
			<li
				class="flex items-start gap-2 border-t border-dashed border-line-dashed py-1.5 first:border-t-0"
			>
				<label class="sr-only" for={`${list}-${i}`}>{opts.noun} {i + 1}</label>
				<textarea
					id={`${list}-${i}`}
					data-line={list}
					rows="1"
					value={line}
					oninput={(e) => setLine(list, i, e.currentTarget.value)}
					maxlength={opts.maxLength}
					placeholder={opts.example}
					class={[lineField, blankOr(line)]}></textarea>
				<button
					type="button"
					aria-label={`Remove ${opts.noun.toLowerCase()} ${i + 1}${line ? `, ${line}` : ''}`}
					class={removeButton}
					onclick={() => removeLine(list, i)}><Icon name="close" size={16} /></button
				>
			</li>
		{/each}
	</ul>
	{#if items.length < opts.max}
		<button type="button" class={addButton} onclick={() => addLine(list)}>
			<Icon name="plus" size={14} />{opts.add}
		</button>
	{/if}
{/snippet}

<div bind:this={editor} class="flex flex-col gap-4">
	<Panel title="Topics">
		{#snippet actions()}{@render cap(config.topics.length, MAX_TOPICS)}{/snippet}
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
						class={removeButton}
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
					class="h-control-md min-w-0 flex-1 rounded-sm border border-control bg-surface px-2.5 text-sm sm:w-72 sm:flex-none"
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

	<Panel title="What's true">
		{#snippet actions()}
			{@render cap(facts.length, MAX_FACTS)}{@render help('Herald checks emails against these.')}
		{/snippet}
		{@render lines('facts', facts, {
			noun: 'Fact',
			max: MAX_FACTS,
			maxLength: MAX_FACT_LENGTH,
			example: 'Returns are accepted within 7 days of delivery.',
			add: 'Add a fact'
		})}
	</Panel>

	<Panel title="What matters most">
		{#snippet actions()}
			{@render cap(guidance.length, MAX_GUIDANCE)}{@render help('How Herald judges urgency.')}
		{/snippet}
		{@render lines('guidance', guidance, {
			noun: 'Guidance line',
			max: MAX_GUIDANCE,
			maxLength: MAX_GUIDANCE_LENGTH,
			example: 'Wedding planners are always important.',
			add: 'Add a line'
		})}
	</Panel>

	<Panel title="What happens">
		{#snippet actions()}
			{@render cap(rules.length, MAX_RULES)}
			<!-- decide.py checks alert rules before close rules, so this holds whatever the order. -->
			{@render help('If two rules match, Alert me wins over Close quietly.')}
		{/snippet}
		<div
			class="mb-2 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md bg-floor-bg px-3.5 py-3 text-floor-fg"
		>
			<Icon name="shield" size={18} />
			<p class="min-w-0 grow basis-60 text-md">
				<b>Always</b>, when an email is about safety, a hacked account or a legal threat,
				<b>alert me</b>.
			</p>
			<span class="rounded-xs border border-current px-1.5 text-xs font-bold"
				>Can't be switched off</span
			>
		</div>
		{#if !rules.length}
			<p class="px-2 py-2 text-sm text-muted">
				No rules yet. Herald still alerts you for urgent emails and very angry customers.
			</p>
		{/if}
		<ul>
			{#each rules as rule, i (rule.id)}
				{@const choice = actionChoice(rule)}
				<li
					class="flex items-start gap-2 border-t border-dashed border-line-dashed py-3 first:border-t-0"
				>
					<div class="flex min-w-0 flex-1 flex-col gap-1">
						<label class="sr-only" for={`rule-name-${rule.id}`}>Rule name</label>
						<input
							id={`rule-name-${rule.id}`}
							bind:value={config.rules![i].name}
							placeholder="Name this rule"
							class={[
								'h-7 w-72 max-w-full rounded-sm border px-2 text-sm font-bold text-muted focus:border-control focus:text-ink',
								blankOr(rule.name)
							]}
						/>
						<div class="flex flex-wrap items-center gap-2 px-2">
							<label class="font-bold" for={`rule-when-${rule.id}`}>When</label>
							<textarea
								id={`rule-when-${rule.id}`}
								data-rule-when
								rows="1"
								bind:value={config.rules![i].when}
								placeholder="the customer says the cake arrived damaged"
								class="field-sizing-content min-w-0 grow basis-80 resize-none rounded-sm border border-dashed border-control bg-surface px-2.5 py-1.5 text-md leading-snug font-semibold focus:border-solid"
							></textarea>
							<label class="font-bold" for={`rule-then-${rule.id}`}>then</label>
							<select
								id={`rule-then-${rule.id}`}
								value={choice}
								onchange={(e) => (config.rules![i] = withChoice(rule, e.currentTarget.value))}
								class={[
									'h-control-md cursor-pointer rounded-sm border-[1.5px] border-current px-2 text-sm font-bold',
									TONE_CLASSES[ACTION_TONE[rule.action]]
								]}
							>
								<option value="alert">Alert me</option>
								<optgroup label="Set urgency">
									{#each Object.entries(URGENCY) as [value, { label }] (value)}
										<option value={`set_urgency:${value}`}>Set urgency: {label}</option>
									{/each}
								</optgroup>
								<option value="close">Close quietly</option>
							</select>
						</div>
					</div>
					<button
						type="button"
						aria-label={`Remove ${rule.name || 'this rule'}`}
						class={removeButton}
						onclick={() => (config.rules = rules.filter((r) => r.id !== rule.id))}
						><Icon name="close" size={16} /></button
					>
				</li>
			{/each}
		</ul>
		{#if rules.length < MAX_RULES}
			<button type="button" class={addButton} onclick={addRule}>
				<Icon name="plus" size={14} />Add a rule
			</button>
		{/if}
	</Panel>
</div>
