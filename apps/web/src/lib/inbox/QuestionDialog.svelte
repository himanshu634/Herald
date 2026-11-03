<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { Email, Rule, TryOut, WorkspaceConfig } from '#lib/api/client.js';
	import { MAX_RULES, actionChoice, newRule, withChoice } from '#lib/setup/setup.js';
	import {
		Button,
		Dialog,
		Icon,
		STATUS,
		StatusTag,
		TONE_CLASSES,
		Tag,
		URGENCY,
		type Tone
	} from '#lib/ui/index.js';
	import {
		countChanges,
		draftOf,
		factMark,
		putFact,
		putRule,
		ruleMark,
		ruleProblem,
		withDraft,
		type Draft,
		type Edit,
		type Mark
	} from './draft';
	import {
		ACTIONS,
		MAX_FACTS,
		MAX_FACT_LENGTH,
		questionActionsFor,
		formatTime,
		highlight,
		tidyBody,
		type Action
	} from './inbox';

	let {
		email,
		config,
		busy,
		ontry,
		onkeep,
		onact,
		onclose
	}: {
		email: Email;
		/** The business's saved config. The dialog edits a draft of its facts and rules. */
		config: WorkspaceConfig;
		busy: boolean;
		/** Read the email with this config and say what Herald would do. Saves nothing. */
		ontry: (config: WorkspaceConfig) => Promise<TryOut>;
		/** Save this config (null: nothing changed), then have Herald read the email again. */
		onkeep: (config: WorkspaceConfig | null) => void;
		onact: (action: Action) => void;
		onclose: () => void;
	} = $props();

	// Seeded once: the parent keys this dialog by email, so another email starts afresh.
	// svelte-ignore state_referenced_locally
	let draft = $state.raw<Draft>(draftOf(config));
	// What the side panel has open, and its own copy, so Cancel leaves the draft alone.
	let edit = $state.raw<Edit | null>(null);
	let factText = $state('');
	let replace = $state<number | null>(null);
	let rule = $state<Rule | null>(null);

	// A try belongs to the draft it was run on. Any later edit makes it stale, so it hides.
	let tried = $state.raw<{ result: TryOut; key: string } | null>(null);
	let trying = $state(false);
	let tryError = $state<string | null>(null);

	const saved = $derived(draftOf(config));
	const key = $derived(JSON.stringify(draft));
	const result = $derived(tried?.key === key ? tried.result : null);
	const changes = $derived(countChanges(config, draft));
	const quotes = $derived(email.notes?.quotes?.map((q) => tidyBody(q.text)).filter(Boolean) ?? []);
	const parts = $derived(highlight(tidyBody(email.body), quotes));
	const actions = $derived(questionActionsFor(email.status));
	const atCap = $derived(draft.facts.length >= MAX_FACTS);
	const newFactAtCap = $derived(edit?.kind === 'fact' && edit.index === null && atCap);
	const panelProblem = $derived.by(() => {
		if (edit?.kind === 'rule') return rule ? ruleProblem(rule) : null;
		if (edit?.kind !== 'fact') return null;
		if (edit.index === null && !factText.trim()) return 'Write the fact first.';
		if (newFactAtCap && replace === null) return 'Pick the fact this one replaces.';
		return null;
	});

	// The action tag is tinted like the status it leads to, as in the setup editor.
	const ACTION_TAG: Record<Rule['action'], Tone> = {
		alert: 'danger',
		set_urgency: 'warning',
		close: 'neutral'
	};

	function actionLabel(r: Rule): string {
		if (r.action === 'alert') return 'Alert me';
		if (r.action === 'close') return 'Close quietly';
		return r.urgency ? URGENCY[r.urgency].label : 'Set urgency';
	}

	function openFact(index: number | null, text?: string) {
		edit = { kind: 'fact', index };
		factText = text ?? (index === null ? '' : draft.facts[index]);
		replace = null;
	}

	function openRule(id: string | null) {
		const found = draft.rules.find((r) => r.id === id);
		rule = found ? { ...found } : newRule(draft.rules);
		edit = { kind: 'rule', id };
	}

	function closePanel() {
		edit = null;
		rule = null;
	}

	function keepPanel() {
		if (!edit || panelProblem) return;
		if (edit.kind === 'fact')
			draft = { ...draft, facts: putFact(draft.facts, edit.index, factText, replace) };
		else if (rule) draft = { ...draft, rules: putRule(draft.rules, rule) };
		closePanel();
	}

	function removeItem() {
		if (edit?.kind === 'fact' && edit.index !== null)
			draft = { ...draft, facts: putFact(draft.facts, edit.index, '') };
		else if (edit?.kind === 'rule' && edit.id !== null) {
			const id = edit.id;
			draft = { ...draft, rules: draft.rules.filter((r) => r.id !== id) };
		}
		closePanel();
	}

	function undoAll() {
		draft = draftOf(config);
		tried = null;
		tryError = null;
		closePanel();
	}

	async function tryIt() {
		if (trying || !changes) return;
		trying = true;
		tryError = null;
		const ran = key;
		try {
			tried = { result: await ontry(withDraft(config, draft)), key: ran };
		} catch {
			tryError = 'Herald couldn’t try it just now. Your changes are still here; try again.';
		} finally {
			trying = false;
		}
	}

	function isOpen(kind: 'fact' | 'rule', at: number | string) {
		if (edit?.kind !== kind) return false;
		return edit.kind === 'fact' ? edit.index === at : edit.id === at;
	}
</script>

{#snippet mark(value: Mark)}
	{#if value === 'new'}<Tag tone="accent">New</Tag>{:else if value === 'changed'}<span
			class="inline-flex h-5 items-center rounded-xs bg-ink px-1.5 text-xs leading-none font-semibold whitespace-nowrap text-canvas"
			>Changed</span
		>{/if}
{/snippet}

{#snippet row(label: string, open: boolean, onclick: () => void, body: Snippet)}
	<button
		type="button"
		aria-label={label}
		aria-pressed={open}
		{onclick}
		class={[
			'group flex min-h-8 w-full cursor-pointer items-center gap-2 rounded-sm border px-2 py-1 text-left text-sm hover:bg-surface',
			open ? 'border-ink bg-surface shadow-[0_2px_0_var(--color-ink)]' : 'border-transparent'
		]}
	>
		{@render body()}
		<span
			aria-hidden="true"
			class="flex size-6 flex-none items-center justify-center rounded-xs text-muted group-hover:text-ink"
			><Icon name="pencil" size={14} /></span
		>
	</button>
{/snippet}

{#snippet panel()}
	{#if edit}
		{@const isFact = edit.kind === 'fact'}
		{@const isNew = edit.kind === 'fact' ? edit.index === null : edit.id === null}
		{@const title = isFact
			? isNew
				? 'New fact'
				: `Change fact ${(edit.kind === 'fact' ? edit.index! : 0) + 1}`
			: isNew
				? 'New rule'
				: 'Change rule'}
		<section aria-label={title} class="flex min-h-0 flex-1 flex-col">
			<div
				class="flex flex-none items-center justify-between gap-3 border-b border-dashed border-line-dashed px-5 py-4"
			>
				<h3 class="text-lg font-extrabold">{title}</h3>
				<button
					type="button"
					class="inline-flex size-control-md flex-none cursor-pointer items-center justify-center rounded-sm border border-line text-neutral-fg hover:bg-subtle"
					aria-label="Close the panel"
					onclick={closePanel}><Icon name="close" size={16} /></button
				>
			</div>
			<div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
				{#if edit.kind === 'fact'}
					{#if edit.index !== null && saved.facts[edit.index] !== undefined && saved.facts[edit.index] !== factText}
						<div>
							<p class="text-xs font-bold text-muted">Saved now</p>
							<p class="text-sm text-muted line-through">{saved.facts[edit.index]}</p>
						</div>
					{/if}
					<div class="flex flex-col gap-1.5">
						<label for="panel-fact" class="text-sm font-bold">
							{edit.index === null ? 'New fact' : `Fact ${edit.index + 1}`}
						</label>
						<textarea
							id="panel-fact"
							{@attach (node) => node.focus()}
							bind:value={factText}
							maxlength={MAX_FACT_LENGTH}
							rows="4"
							placeholder="One plain line, like: Returns are accepted within 30 days."
							class="w-full resize-y rounded-sm border border-control bg-surface px-2.5 py-2 text-md"
						></textarea>
						<p class="text-xs text-muted">
							One plain line, up to {MAX_FACT_LENGTH} characters. {factText.length} used.
						</p>
					</div>
					{#if email.notes?.fact_draft && factText !== email.notes.fact_draft}
						<Button
							variant="quiet"
							size="sm"
							class="self-start"
							onclick={() => (factText = email.notes?.fact_draft ?? '')}>Use Herald’s draft</Button
						>
					{/if}
					{#if newFactAtCap}
						<fieldset class="flex flex-col gap-1">
							<legend class="mb-1 text-sm font-bold">
								You have {MAX_FACTS} facts, the most Herald keeps. This one replaces:
							</legend>
							{#each draft.facts as fact, i (i)}
								<label
									class={[
										'flex cursor-pointer items-start gap-2 rounded-sm px-2 py-1.5 text-sm',
										replace === i && 'bg-danger-bg'
									]}
								>
									<input type="radio" name="replace" value={i} bind:group={replace} class="mt-1" />
									<span class="w-4 flex-none text-xs font-bold text-muted">{i + 1}</span>
									<span class={['min-w-0 flex-1', replace === i && 'text-muted line-through']}
										>{fact}</span
									>
								</label>
							{/each}
						</fieldset>
					{/if}
				{:else if rule}
					<div class="flex flex-col gap-1.5">
						<label for="panel-rule-name" class="text-sm font-bold">Name</label>
						<input
							id="panel-rule-name"
							{@attach (node) => node.focus()}
							bind:value={rule.name}
							placeholder="Name this rule"
							class="h-control-md w-full rounded-sm border border-control bg-surface px-2.5 text-md"
						/>
					</div>
					<div class="flex flex-col gap-1.5">
						<label for="panel-rule-when" class="text-sm font-bold">When</label>
						<textarea
							id="panel-rule-when"
							bind:value={rule.when}
							rows="3"
							placeholder="the customer asks about buying more pairs"
							class="w-full resize-y rounded-sm border border-dashed border-control bg-surface px-2.5 py-2 text-md font-semibold focus:border-solid"
						></textarea>
					</div>
					<div class="flex flex-wrap items-center gap-2">
						<label for="panel-rule-then" class="text-sm font-bold">then</label>
						<select
							id="panel-rule-then"
							value={actionChoice(rule)}
							onchange={(e) => rule && (rule = withChoice(rule, e.currentTarget.value))}
							class={[
								'h-control-md cursor-pointer rounded-sm border-[1.5px] border-current px-2 text-sm font-bold',
								TONE_CLASSES[ACTION_TAG[rule.action]]
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
					<p
						class="flex items-start gap-2 rounded-md bg-warning-bg px-3 py-2.5 text-sm text-warning-fg"
					>
						<Icon name="alert" size={16} />
						<span>
							Rules apply to every new email, not just this one. If two rules match, Alert me wins
							over Close quietly.
						</span>
					</p>
				{/if}
			</div>
			<div class="flex flex-none flex-col gap-2 border-t border-line px-5 py-3">
				<!-- One line that changes its words, not its size, so the buttons never jump. -->
				<p class="truncate text-xs text-muted" aria-live="polite">
					{panelProblem ?? 'Nothing is saved until you keep your changes in the dialog.'}
				</p>
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div class="flex items-center gap-3">
						<Button variant="primary" disabled={!!panelProblem} onclick={keepPanel}
							>Keep in draft</Button
						>
						<Button variant="quiet" onclick={closePanel}>Cancel</Button>
					</div>
					{#if !isNew}
						<Button variant="quiet" onclick={removeItem}
							><span class="text-danger-fg">Remove {isFact ? 'fact' : 'rule'}</span></Button
						>
					{/if}
				</div>
			</div>
		</section>
	{/if}
{/snippet}

<Dialog
	open
	label="Herald is unsure about this email"
	{onclose}
	onescape={() => {
		if (!edit) return false;
		closePanel();
		return true;
	}}
	aside={edit ? panel : undefined}
>
	{#snippet header()}
		<p class="truncate text-xs text-muted">{email.sender}, {formatTime(email.received_at)}</p>
		<div class="mt-1 flex flex-wrap items-center gap-3">
			<h2 class="text-xl font-extrabold">{email.subject}</h2>
			<StatusTag status={email.status} />
		</div>
	{/snippet}

	<section
		aria-label="The email and Herald’s question"
		class="flex min-w-0 flex-col gap-4 px-5 py-4 md:flex-1 md:overflow-y-auto"
	>
		{#if trying}
			<div
				role="status"
				class="flex items-center gap-3 rounded-lg border-[1.5px] border-ink bg-neutral-bg px-4 py-3 font-bold"
			>
				<span
					aria-hidden="true"
					class="size-4.5 animate-spin rounded-full border-[2.5px] border-line-strong border-t-ink motion-reduce:animate-none"
				></span>
				Herald is trying your changes on this email…
			</div>
		{:else if result}
			<!-- A rule can move an email Herald is still unsure about, so "moved" and "sure" are
				told apart: the question stays up until the owner handles it either way. -->
			{@const moved = result.status !== email.status}
			{@const sure = result.notes?.sure !== false}
			<div
				role="status"
				class="overflow-hidden rounded-lg border-[1.5px] border-ink shadow-[0_3px_0_var(--color-ink)]"
			>
				<p
					class={[
						'flex items-center gap-2 px-4 py-3 text-lg font-extrabold',
						moved || sure ? 'bg-success-bg text-success-fg' : 'bg-warning-bg text-warning-fg'
					]}
				>
					<Icon name={moved || sure ? 'check' : 'info'} size={18} />
					{moved
						? `With your changes, it goes to ${STATUS[result.status].label}`
						: sure
							? `Herald is sure now. It stays in ${STATUS[result.status].label}`
							: `No change: still unsure, still in ${STATUS[result.status].label}`}
				</p>
				<div class="flex flex-col gap-3 bg-surface px-4 py-3">
					<p class="text-sm text-muted">
						A trial read. Nothing is saved and the email has not moved.
					</p>
					<div class="grid overflow-hidden rounded-md border border-line sm:grid-cols-2">
						{#each [{ title: 'Now', status: email.status, decision: email.decision }, { title: 'With your changes', status: result.status, decision: result.decision }] as side, i (side.title)}
							<div
								class={[
									'flex flex-col gap-2 px-3.5 py-3',
									i === 1 && 'border-line bg-accent-soft max-sm:border-t sm:border-l'
								]}
							>
								<p class="text-xs font-bold text-muted">{side.title}</p>
								<dl class="grid grid-cols-[4.5rem_1fr] gap-y-1.5 text-sm">
									<dt class="text-muted">Status</dt>
									<dd><StatusTag status={side.status} /></dd>
									<dt class="text-muted">Why</dt>
									<dd class="font-semibold">{side.decision?.reason ?? '—'}</dd>
									<dt class="text-muted">Urgency</dt>
									<dd class="font-semibold">
										{side.decision?.urgency ? URGENCY[side.decision.urgency].label : '—'}
									</dd>
								</dl>
							</div>
						{/each}
					</div>
					{#if !sure}
						<p class="text-md font-bold">
							Herald is still unsure{result.notes?.question
								? `. It asks: ${result.notes.question}`
								: '.'}
						</p>
						{#if moved}
							<p class="text-sm text-muted">The question stays until you mark it On it or Done.</p>
						{/if}
					{/if}
				</div>
			</div>
		{:else if tryError}
			<p role="alert" class="rounded-md bg-danger-bg px-4 py-3 text-sm text-danger-fg">
				{tryError}
			</p>
		{/if}

		<div class="flex items-start gap-3 rounded-lg bg-ink px-4 py-3 text-canvas">
			<span
				aria-hidden="true"
				class="flex size-7 flex-none items-center justify-center rounded-md bg-accent text-lg font-extrabold text-on-accent"
				>?</span
			>
			<div>
				<h3 class="text-lg leading-snug font-bold">
					{email.notes?.question ?? 'Herald isn’t sure how you’d want this one handled.'}
				</h3>
				<p class="mt-1 text-sm opacity-80">
					Answer with a fact or a rule. Herald reads both on every email, so the next one like this
					is sorted without asking.
				</p>
			</div>
		</div>

		{#if email.notes?.fact_draft}
			<div
				class="flex flex-col gap-2 rounded-lg border-[1.5px] border-dashed border-accent-base bg-accent-soft p-3"
			>
				<div class="flex flex-wrap items-center justify-between gap-2">
					<p class="text-sm font-bold">Herald’s draft fact. It isn’t saved yet</p>
					<Button size="sm" onclick={() => openFact(null, email.notes?.fact_draft ?? '')}>
						{atCap ? 'Use to change a fact' : 'Use as a fact'}
					</Button>
				</div>
				<p class="text-md">{email.notes.fact_draft}</p>
			</div>
		{/if}

		<div class="flex flex-col gap-2">
			<h3 class="text-sm font-bold text-muted">The email</h3>
			<p class="text-md whitespace-pre-line text-body">
				{#each parts as part, i (i)}{#if part.quoted}<mark
							class="rounded-[2px] bg-accent-tint px-0.5 text-ink shadow-[inset_0_-2px_0_var(--color-accent-base)]"
							>{part.text}</mark
						>{:else}{part.text}{/if}{/each}
			</p>
		</div>
	</section>

	<aside
		aria-label="What Herald knows"
		class="flex min-w-0 flex-col gap-4 border-line bg-sunken px-4 py-4 max-md:border-t md:w-[22rem] md:flex-none md:overflow-y-auto md:border-l"
	>
		<h3 class="text-md font-extrabold">What Herald knows</h3>
		<p class="flex items-center gap-2 rounded-md bg-floor-bg px-3 py-2 text-xs text-floor-fg">
			<Icon name="lock" size={14} />
			<span>Always alerts on safety, a hacked account or a legal threat.</span>
		</p>

		<div class="flex flex-col gap-0.5">
			<div class="flex items-center justify-between gap-2">
				<h4 class="text-sm font-extrabold">Your rules · {draft.rules.length}</h4>
				{#if draft.rules.length < MAX_RULES}
					<Button variant="quiet" size="sm" onclick={() => openRule(null)}>
						<Icon name="plus" size={14} />Add a rule
					</Button>
				{/if}
			</div>
			{#each draft.rules as r (r.id)}
				{#snippet body()}
					<span class="min-w-0 flex-1 truncate font-bold">{r.name}</span>
					{@render mark(ruleMark(saved.rules, r))}
					<Tag tone={ACTION_TAG[r.action]}>{actionLabel(r)}</Tag>
				{/snippet}
				{@render row(`Change rule ${r.name}`, isOpen('rule', r.id), () => openRule(r.id), body)}
			{:else}
				<p class="px-2 py-1 text-sm text-muted">
					No rules yet. Add one to alert you, set urgency or close mail like this.
				</p>
			{/each}
		</div>

		<div class="flex flex-col gap-0.5">
			<div class="flex items-center justify-between gap-2">
				<h4 class="text-sm font-extrabold">Your facts · {draft.facts.length} of {MAX_FACTS}</h4>
				<Button variant="quiet" size="sm" onclick={() => openFact(null)}>
					<Icon name="plus" size={14} />Add a fact
				</Button>
			</div>
			{#each draft.facts as fact, i (i)}
				{#snippet body()}
					<span class="w-4 flex-none text-xs font-bold text-muted">{i + 1}</span>
					<span class="min-w-0 flex-1 truncate text-body">{fact}</span>
					{@render mark(factMark(saved.facts, draft.facts, i))}
				{/snippet}
				{@render row(`Change fact ${i + 1}: ${fact}`, isOpen('fact', i), () => openFact(i), body)}
			{:else}
				<p class="px-2 py-1 text-sm text-muted">No facts yet.</p>
			{/each}
		</div>
	</aside>

	{#snippet footer()}
		<div class="flex flex-wrap items-center gap-3">
			{#if !changes}
				<Button disabled={busy} onclick={() => onkeep(null)}>
					<Icon name="redo" size={15} />Rerun Herald
				</Button>
				<Button variant="quiet" onclick={onclose}>Not now</Button>
			{:else}
				<Tag tone="neutral">{changes} {changes === 1 ? 'change' : 'changes'}, not saved</Tag>
				{#if result}
					<Button variant="primary" disabled={busy} onclick={() => onkeep(withDraft(config, draft))}
						>Keep {changes === 1 ? 'change' : 'changes'} and rerun</Button
					>
				{:else}
					<Button variant="primary" disabled={busy || trying} onclick={tryIt}>
						<Icon name="redo" size={15} />{trying ? 'Trying…' : 'Try on this email'}
					</Button>
					<Button
						variant="quiet"
						disabled={busy || trying}
						onclick={() => onkeep(withDraft(config, draft))}>Keep without trying</Button
					>
				{/if}
				<Button variant="quiet" onclick={undoAll}>Undo all</Button>
			{/if}
		</div>
		<div class="flex flex-wrap gap-2">
			{#each actions as action (action)}
				<Button disabled={busy} onclick={() => onact(action)}>{ACTIONS[action].label}</Button>
			{/each}
		</div>
	{/snippet}
</Dialog>
