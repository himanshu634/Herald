<script lang="ts">
	import type { Email } from '#lib/api/client.js';
	import { AngerMeter, StatusTag, Tag, URGENCY } from '#lib/ui/index.js';
	import { floorLabel, formatTime, senderName } from './inbox';

	let {
		emails,
		selectedId,
		onselect
	}: { emails: Email[]; selectedId: string | null; onselect: (id: string) => void } = $props();

	const th = 'h-8.5 border-b border-line bg-sunken px-3 text-left text-xs font-bold text-muted';
	const td = 'h-row border-b border-dashed border-line-dashed px-3 whitespace-nowrap';
</script>

<div class="overflow-x-auto rounded-lg border border-line bg-surface">
	<table class="w-full min-w-176 border-collapse text-sm">
		<thead>
			<tr>
				<th class={th}>Status</th>
				<th class={th}>From</th>
				<th class={th}>Summary</th>
				<th class={[th, 'max-2xl:hidden']}>Topic</th>
				<th class={th}>Urgency</th>
				<th class={th}>Anger</th>
				<th class={th}>Why</th>
				<th class={[th, 'text-right']}>Time</th>
			</tr>
		</thead>
		<tbody>
			{#each emails as email (email.id)}
				{@const selected = email.id === selectedId}
				{@const urgency = email.decision?.urgency ?? email.notes?.urgency}
				{@const floor = floorLabel(email.decision?.floor_flags ?? [])}
				<!-- A mouse shortcut: the sender button in the row is the accessible control. -->
				<tr
					class={['cursor-pointer', selected ? 'bg-accent-soft' : 'hover:bg-sunken']}
					onclick={() => onselect(email.id)}
				>
					<td class={[td, selected && 'shadow-[inset_3px_0_0_var(--color-accent)]']}>
						<StatusTag status={email.status} />
					</td>
					<td class={[td, 'font-bold']}>
						<!-- The real control for keyboard and screen readers; the row click is a shortcut. -->
						<button
							type="button"
							class="cursor-pointer text-left font-bold"
							aria-current={selected}
							onclick={(event) => {
								event.stopPropagation();
								onselect(email.id);
							}}>{senderName(email.sender)}</button
						>
					</td>
					<td class={[td, 'max-w-60 truncate']} title={email.notes?.summary ?? email.subject}>
						{email.notes?.summary ?? email.subject}
					</td>
					<td class={[td, 'text-body max-2xl:hidden']}>{email.notes?.topic ?? ''}</td>
					<td class={td}>
						{#if urgency}<Tag tone={URGENCY[urgency].tone}>{URGENCY[urgency].label}</Tag>{/if}
					</td>
					<td class={td}>
						{#if email.notes}<AngerMeter level={email.notes.anger} />{/if}
					</td>
					<td class={[td, 'max-w-36 truncate text-body']}>
						{#if floor}
							<Tag tone="floor" icon="shield">Safety floor</Tag>
						{:else if email.decision}
							{email.decision.reason}
						{:else}
							<span class="text-muted">Herald is reading</span>
						{/if}
					</td>
					<td class={[td, 'text-right text-muted']}>{formatTime(email.received_at)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
