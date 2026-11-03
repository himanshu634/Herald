<script lang="ts">
	import type { Email } from '#lib/api/client.js';
	import { AngerMeter, Button, Icon, StatusTag, Tag, URGENCY } from '#lib/ui/index.js';
	import {
		ACTIONS,
		actionsFor,
		floorLabel,
		formatTime,
		highlight,
		tidyBody,
		type Action
	} from './inbox';

	let {
		email,
		busy,
		full,
		ontogglefull,
		onact
	}: {
		email: Email;
		busy: boolean;
		/** The owner asked to read the whole email (the E key or the button). */
		full: boolean;
		ontogglefull: () => void;
		onact: (action: Action) => void;
	} = $props();

	const floor = $derived(floorLabel(email.decision?.floor_flags ?? []));
	const urgency = $derived(email.decision?.urgency ?? email.notes?.urgency);
	const quotes = $derived(email.notes?.quotes?.map((q) => tidyBody(q.text)).filter(Boolean) ?? []);
	// Quotes are tidied the same way as the body, so a quote that spans lines still matches.
	const parts = $derived(highlight(tidyBody(email.body), quotes));
	// With no notes there is no summary to read instead, so the email shows in full.
	const showFull = $derived(full || !email.notes);
	const actions = $derived(actionsFor(email.status));
	const otherFlags = $derived(
		(email.notes?.risk_flags ?? []).includes('about_to_cancel') ? ['About to cancel'] : []
	);
</script>

<aside
	aria-label="Herald on this email"
	class="flex min-w-0 flex-1 flex-col rounded-lg border border-line bg-surface lg:overflow-y-auto"
>
	<header class="border-b border-dashed border-line-dashed px-5 py-4">
		<div class="flex items-center justify-between gap-3">
			<p class="truncate text-xs text-muted">{email.sender}, {formatTime(email.received_at)}</p>
			<StatusTag status={email.status} />
		</div>
		<h2 class="mt-1 text-xl font-extrabold">{email.subject}</h2>
	</header>

	<!-- One card: its parts are split by dashed dividers, never cards inside the card. -->
	<div class="flex flex-1 flex-col">
		<section aria-labelledby="why-title" class="px-5 py-4">
			{#if floor}
				<div class="mb-4 flex items-start gap-3 rounded-lg bg-floor-bg px-4 py-3 text-floor-fg">
					<Icon name="shield" size={18} />
					<p class="text-sm">{floor}. This always alerts you, whatever your rules say.</p>
				</div>
			{/if}

			<h3 id="why-title" class="mb-2 text-sm font-bold text-muted">Why it's here</h3>
			{#if email.decision}
				<p class="text-md font-bold">{floor ?? email.decision.reason}</p>
			{:else}
				<p class="text-sm text-muted">Herald is reading this email.</p>
			{/if}

			{#if email.notes}
				{#if email.notes.summary}
					<p class="mt-2 text-md text-body">{email.notes.summary}</p>
				{/if}

				{#if quotes.length}
					<ul class="mt-3 flex flex-col gap-2" aria-label="What the email says">
						{#each quotes as quote, i (i)}
							<li
								class="rounded-xs bg-accent-tint px-3 py-2 text-sm text-ink shadow-[inset_2px_0_0_var(--color-accent-base)]"
							>
								{quote}
							</li>
						{/each}
					</ul>
				{/if}

				<dl
					class="mt-4 grid grid-cols-[6rem_1fr] gap-x-3 gap-y-2 border-t border-dashed border-line-dashed pt-4 text-sm"
				>
					<dt class="text-muted">Topic</dt>
					<dd>{email.notes.topic}</dd>
					<dt class="text-muted">Urgency</dt>
					<dd>
						{#if urgency}<Tag tone={URGENCY[urgency].tone}>{URGENCY[urgency].label}</Tag>{/if}
					</dd>
					<dt class="text-muted">Anger</dt>
					<dd><AngerMeter level={email.notes.anger} showLabel /></dd>
					<dt class="text-muted">Herald is</dt>
					<dd>{email.notes.sure ? 'Sure' : 'Unsure, so it asks you'}</dd>
					{#if otherFlags.length}
						<dt class="text-muted">Flags</dt>
						<dd class="flex gap-1">
							{#each otherFlags as flag (flag)}<Tag tone="neutral">{flag}</Tag>{/each}
						</dd>
					{/if}
				</dl>
			{/if}
		</section>

		<section
			aria-labelledby="email-title"
			class="border-t border-dashed border-line-dashed px-5 py-4"
		>
			<div class="mb-2 flex items-center justify-between gap-3">
				<h3 id="email-title" class="text-sm font-bold text-muted">The email</h3>
				{#if email.notes}
					<Button
						variant="quiet"
						size="sm"
						kbd="E"
						aria-expanded={showFull}
						aria-controls="email-body"
						onclick={ontogglefull}>{showFull ? 'Hide' : 'Read it all'}</Button
					>
				{/if}
			</div>
			{#if showFull}
				<p id="email-body" class="text-md whitespace-pre-line text-body">
					{#each parts as part, i (i)}{#if part.quoted}<mark
								class="rounded-[2px] bg-accent-tint px-0.5 text-ink shadow-[inset_0_-2px_0_var(--color-accent-base)]"
								>{part.text}</mark
							>{:else}{part.text}{/if}{/each}
				</p>
			{:else}
				<!-- A short preview; the owner opens the rest only when the summary is not enough. -->
				<button
					id="email-body"
					type="button"
					class="line-clamp-3 w-full cursor-pointer text-left text-sm text-muted hover:text-body"
					onclick={ontogglefull}>{tidyBody(email.body).replace(/\s*\n\s*/g, ' ')}</button
				>
			{/if}
		</section>

		{#if actions.length}
			<div class="mt-auto flex flex-wrap gap-2 border-t border-dashed border-line-dashed px-5 py-4">
				{#each actions as action, i (action)}
					<Button
						variant={i === 0 ? 'primary' : 'secondary'}
						kbd={ACTIONS[action].key}
						disabled={busy}
						onclick={() => onact(action)}>{ACTIONS[action].label}</Button
					>
				{/each}
			</div>
		{/if}
	</div>
</aside>
