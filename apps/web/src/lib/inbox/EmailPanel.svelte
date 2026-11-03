<script lang="ts">
	import type { Email } from '#lib/api/client.js';
	import { AngerMeter, Button, Icon, StatusTag, Tag, URGENCY } from '#lib/ui/index.js';
	import { ACTIONS, actionsFor, floorLabel, formatTime, highlight, type Action } from './inbox';

	let { email, busy, onact }: { email: Email; busy: boolean; onact: (action: Action) => void } =
		$props();

	const floor = $derived(floorLabel(email.decision?.floor_flags ?? []));
	const urgency = $derived(email.decision?.urgency ?? email.notes?.urgency);
	const parts = $derived(highlight(email.body, email.notes?.quotes?.map((q) => q.text) ?? []));
	const actions = $derived(actionsFor(email.status));
	const otherFlags = $derived(
		(email.notes?.risk_flags ?? []).includes('about_to_cancel') ? ['About to cancel'] : []
	);
</script>

<aside
	aria-label="Herald on this email"
	class="flex min-w-0 flex-1 flex-col border-l border-line bg-surface max-lg:border-t max-lg:border-l-0 lg:overflow-y-auto"
>
	<header class="border-b border-dashed border-line-dashed px-5 py-4">
		<div class="flex items-center justify-between gap-3">
			<p class="truncate text-xs text-muted">{email.sender}, {formatTime(email.received_at)}</p>
			<StatusTag status={email.status} />
		</div>
		<h2 class="mt-1 text-xl font-extrabold">{email.subject}</h2>
	</header>

	<div class="flex flex-1 flex-col gap-4 px-5 py-4">
		{#if floor}
			<div class="flex items-start gap-3 rounded-lg bg-floor-bg px-4 py-3 text-floor-fg">
				<Icon name="shield" size={18} />
				<p class="text-sm">{floor}. This always alerts you, whatever your rules say.</p>
			</div>
		{/if}

		{#if email.decision}
			<p class="text-sm">
				<span class="text-muted">Why it's here:</span>
				<b>{floor ?? email.decision.reason}</b>
			</p>
		{:else}
			<p class="text-sm text-muted">Herald is reading this email.</p>
		{/if}

		<p class="text-md whitespace-pre-line text-body">
			{#each parts as part, i (i)}{#if part.quoted}<mark
						class="rounded-[2px] bg-accent-tint px-0.5 text-ink shadow-[inset_0_-2px_0_var(--color-accent-base)]"
						>{part.text}</mark
					>{:else}{part.text}{/if}{/each}
		</p>

		{#if email.notes}
			<dl class="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-2 text-sm">
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

		{#if actions.length}
			<div class="mt-auto flex flex-wrap gap-2 pt-2">
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
