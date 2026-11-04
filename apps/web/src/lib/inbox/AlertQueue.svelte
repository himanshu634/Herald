<script lang="ts">
	import type { Email } from '#lib/api/client.js';
	import { Button, Tag } from '#lib/ui/index.js';
	import { floorLabel, formatTime, senderName } from './inbox';

	let {
		alerts,
		selectedId,
		fresh,
		questions,
		onselect,
		onanswer
	}: {
		alerts: Email[];
		selectedId: string | null;
		/** Alerts that arrived while the desk was open and the owner hasn't opened yet. */
		fresh: ReadonlySet<string>;
		/** Herald's questions about mail that is not an alert. */
		questions: Email[];
		onselect: (id: string) => void;
		onanswer: (id: string) => void;
	} = $props();

	function why(email: Email): string {
		return floorLabel(email.decision?.floor_flags ?? []) ?? email.decision?.reason ?? '';
	}
</script>

<nav aria-labelledby="queue-title" class="flex flex-col">
	{#if alerts.length}
		<div class="flex items-baseline justify-between gap-3 px-4 pt-4 pb-2">
			<h2 id="queue-title" class="text-lg font-extrabold">
				{alerts.length === 1 ? '1 alert' : `${alerts.length} alerts`}
			</h2>
			<span class="text-xs text-muted">Worst first</span>
		</div>
		<ul>
			{#each alerts as email (email.id)}
				{@const selected = email.id === selectedId}
				{@const urgent = (email.decision?.urgency ?? email.notes?.urgency) === 'urgent'}
				<li class="border-t border-dashed border-line-dashed first:border-t-0">
					<button
						type="button"
						aria-current={selected}
						class={[
							'grid w-full cursor-pointer grid-cols-[auto_1fr_auto] items-start gap-x-2.5 px-4 py-2.5 text-left text-sm',
							selected
								? 'bg-accent-soft shadow-[inset_3px_0_0_var(--color-accent)]'
								: 'hover:bg-sunken'
						]}
						onclick={() => onselect(email.id)}
					>
						<!-- Urgency in words is in the open alert; the dot only sorts the list by eye. -->
						<span
							aria-hidden="true"
							class={['mt-1.5 size-2 rounded-full', urgent ? 'bg-danger-fg' : 'bg-warning-fg']}
						></span>
						<span class="min-w-0">
							<span class="flex items-center gap-2 font-bold">
								<span class="truncate">{senderName(email.sender)}</span>
								{#if fresh.has(email.id)}<Tag tone="danger">New</Tag>{/if}
							</span>
							<span class="block truncate text-muted">{why(email)}</span>
						</span>
						<span class="text-muted">{formatTime(email.received_at)}</span>
					</button>
				</li>
			{/each}
		</ul>
	{:else}
		<h2 id="queue-title" class="sr-only">Alerts</h2>
	{/if}

	{#if questions.length}
		<section
			aria-labelledby="desk-questions-title"
			class={['flex flex-col gap-1 px-4 py-3', alerts.length && 'border-t border-line']}
		>
			<h3 id="desk-questions-title" class="text-sm font-bold text-muted">
				{questions.length === 1
					? 'Herald has 1 question'
					: `Herald has ${questions.length} questions`}
			</h3>
			{#each questions as email (email.id)}
				<div class="flex items-center gap-3 py-1.5">
					<span
						aria-hidden="true"
						class="flex size-6 flex-none items-center justify-center rounded-sm bg-accent font-extrabold text-on-accent"
						>?</span
					>
					<p class="min-w-0 flex-1 text-sm">
						<span class="line-clamp-2 font-bold"
							>{email.notes?.question ?? 'Herald isn’t sure how you’d want this one handled.'}</span
						>
						<span class="block truncate text-muted">{senderName(email.sender)}</span>
					</p>
					<Button size="sm" onclick={() => onanswer(email.id)}>Answer</Button>
				</div>
			{/each}
		</section>
	{/if}
</nav>
