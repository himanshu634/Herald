<script lang="ts">
	import type { Email } from '#lib/api/client.js';
	import { Button, Dialog, StatusTag } from '#lib/ui/index.js';
	import {
		ACTIONS,
		MAX_FACTS,
		MAX_FACT_LENGTH,
		questionActionsFor,
		formatTime,
		highlight,
		nextFacts,
		tidyBody,
		type Action
	} from './inbox';

	let {
		email,
		facts,
		busy,
		onsave,
		onact,
		onclose
	}: {
		email: Email;
		/** The business's saved facts. */
		facts: string[];
		busy: boolean;
		/** Save these facts, then re-read the email. */
		onsave: (facts: string[]) => void;
		onact: (action: Action) => void;
		onclose: () => void;
	} = $props();

	// Seeded once: the parent keys this dialog by email, so another email starts afresh.
	// svelte-ignore state_referenced_locally
	let draft = $state(email.notes?.fact_draft ?? '');
	// svelte-ignore state_referenced_locally
	let edits = $state([...facts]);
	let editing = $state<number | null>(null);
	let replace = $state<number | null>(null);

	const quotes = $derived(email.notes?.quotes?.map((q) => tidyBody(q.text)).filter(Boolean) ?? []);
	const parts = $derived(highlight(tidyBody(email.body), quotes));
	const atCap = $derived(facts.length >= MAX_FACTS);
	const result = $derived(nextFacts(edits, draft, replace));
	const changed = $derived(JSON.stringify(result.facts) !== JSON.stringify(facts));
	const actions = $derived(questionActionsFor(email.status));

	function pickReplace(index: number) {
		replace = replace === index ? null : index;
	}
</script>

<Dialog open label="Herald is unsure about this email" {onclose}>
	{#snippet header()}
		<p class="truncate text-xs text-muted">{email.sender}, {formatTime(email.received_at)}</p>
		<div class="mt-1 flex flex-wrap items-center gap-3">
			<h2 class="text-xl font-extrabold">{email.subject}</h2>
			<StatusTag status={email.status} />
		</div>
	{/snippet}

	<section
		aria-labelledby="question-email"
		class="flex min-w-0 flex-col gap-3 px-5 py-4 md:flex-[1.1] md:overflow-y-auto"
	>
		<h3 id="question-email" class="text-sm font-bold text-muted">The email</h3>
		<p class="text-md whitespace-pre-line text-body">
			{#each parts as part, i (i)}{#if part.quoted}<mark
						class="rounded-[2px] bg-accent-tint px-0.5 text-ink shadow-[inset_0_-2px_0_var(--color-accent-base)]"
						>{part.text}</mark
					>{:else}{part.text}{/if}{/each}
		</p>
	</section>

	<section
		aria-labelledby="question-title"
		class="flex min-w-0 flex-col gap-4 border-line bg-sunken px-5 py-4 max-md:border-t md:flex-1 md:overflow-y-auto md:border-l"
	>
		<div class="flex items-start gap-3 rounded-lg bg-ink px-4 py-3 text-canvas">
			<span
				aria-hidden="true"
				class="flex size-7 flex-none items-center justify-center rounded-md bg-accent text-lg font-extrabold text-on-accent"
				>?</span
			>
			<div>
				<h3 id="question-title" class="text-lg leading-snug font-bold">
					{email.notes?.question ?? 'Herald isn’t sure how you’d want this one handled.'}
				</h3>
				<p class="mt-1 text-sm opacity-80">
					Answer with a fact. Herald reads your facts on every email, so the next one like this is
					sorted without asking.
				</p>
			</div>
		</div>

		<div
			class={[
				'flex flex-col gap-2 rounded-lg border-[1.5px] border-dashed p-3',
				email.notes?.fact_draft
					? 'border-accent-base bg-accent-soft'
					: 'border-line-strong bg-surface'
			]}
		>
			<div class="flex flex-wrap items-center justify-between gap-2">
				<label for="fact-draft" class="text-sm font-bold">
					{email.notes?.fact_draft ? 'Herald’s draft. Check it, it isn’t saved yet' : 'New fact'}
				</label>
				<span class="text-xs font-bold text-muted">{facts.length} of {MAX_FACTS} facts</span>
			</div>
			<textarea
				id="fact-draft"
				bind:value={draft}
				maxlength={MAX_FACT_LENGTH}
				rows="2"
				placeholder="One plain line, like: Returns are accepted within 30 days."
				class="w-full resize-y rounded-sm border border-control bg-surface px-2.5 py-2 text-md"
			></textarea>
			{#if atCap && draft.trim()}
				<p class="text-sm text-muted">
					{replace === null
						? `You have ${MAX_FACTS} facts, the most Herald keeps. Pick one below to replace, or change one instead.`
						: `Replaces fact ${replace + 1}.`}
				</p>
			{/if}
		</div>

		<div>
			<h4 class="mb-1 text-sm font-bold text-muted">Your facts</h4>
			{#if edits.length}
				<ol class="flex flex-col">
					{#each edits, i (i)}
						<li
							class={[
								'flex items-start gap-2 rounded-sm px-2 py-1.5 text-sm',
								replace === i && 'bg-danger-bg'
							]}
						>
							<span class="w-5 flex-none pt-0.5 text-xs font-bold text-muted">{i + 1}</span>
							{#if editing === i}
								<label class="sr-only" for="fact-{i}">Fact {i + 1}</label>
								<textarea
									id="fact-{i}"
									bind:value={edits[i]}
									maxlength={MAX_FACT_LENGTH}
									rows="2"
									class="min-w-0 flex-1 resize-y rounded-sm border border-ink bg-surface px-2 py-1.5 text-sm"
								></textarea>
								<Button variant="quiet" size="sm" onclick={() => (editing = null)}>Done</Button>
							{:else}
								<p
									class={[
										'min-w-0 flex-1 pt-0.5 text-body',
										replace === i && 'text-muted line-through',
										edits[i] !== facts[i] && 'font-semibold text-ink'
									]}
								>
									{edits[i] || 'Removed'}
								</p>
								{#if atCap && draft.trim()}
									<Button
										variant="quiet"
										size="sm"
										aria-pressed={replace === i}
										onclick={() => pickReplace(i)}>{replace === i ? 'Keep' : 'Replace'}</Button
									>
								{/if}
								<Button variant="quiet" size="sm" onclick={() => (editing = i)}>Change</Button>
							{/if}
						</li>
					{/each}
				</ol>
			{:else}
				<p class="text-sm text-muted">No facts yet. The one above will be the first.</p>
			{/if}
		</div>
	</section>

	{#snippet footer()}
		<div class="flex flex-wrap items-center gap-3">
			<Button
				variant="primary"
				disabled={busy || !changed || !!result.error}
				onclick={() => onsave(result.facts)}>Save and re-read this email</Button
			>
			<Button variant="quiet" onclick={onclose}>Not now</Button>
		</div>
		<div class="flex flex-wrap gap-2">
			{#each actions as action (action)}
				<Button disabled={busy} onclick={() => onact(action)}>{ACTIONS[action].label}</Button>
			{/each}
		</div>
	{/snippet}
</Dialog>
