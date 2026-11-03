<script lang="ts" module>
	import type { Tone } from './tones';

	export type TabItem = { id: string; label: string; count?: number; countTone?: Tone };
</script>

<script lang="ts">
	import Tag from './Tag.svelte';

	let {
		items,
		selected = $bindable(),
		label
	}: { items: TabItem[]; selected?: string; label: string } = $props();

	const current = $derived(selected ?? items[0]?.id);

	// Arrow keys move between tabs (WAI-ARIA tabs pattern, automatic activation).
	function onkeydown(event: KeyboardEvent) {
		const keys: Record<string, number> = { ArrowRight: 1, ArrowLeft: -1 };
		const step = keys[event.key];
		if (!step) return;
		event.preventDefault();
		const index = items.findIndex((item) => item.id === current);
		const next = items[(index + step + items.length) % items.length];
		selected = next.id;
		const list = event.currentTarget as HTMLElement;
		list.querySelector<HTMLButtonElement>(`[data-tab="${next.id}"]`)?.focus();
	}
</script>

<div class="tabs" role="tablist" aria-label={label} tabindex="-1" {onkeydown}>
	{#each items as item (item.id)}
		<button
			type="button"
			role="tab"
			data-tab={item.id}
			class={['tab', item.id === current && 'on']}
			aria-selected={item.id === current}
			tabindex={item.id === current ? 0 : -1}
			onclick={() => (selected = item.id)}
		>
			{item.label}
			{#if item.count !== undefined}
				<Tag tone={item.countTone ?? 'muted'}>{item.count}</Tag>
			{/if}
		</button>
	{/each}
</div>

<style>
	.tabs {
		display: flex;
		gap: var(--space-1);
		overflow-x: auto;
		border-bottom: var(--border-hair) solid var(--color-border);
	}

	.tab {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		height: var(--tab-height);
		padding: 0 var(--space-3);
		margin-bottom: calc(var(--border-hair) * -1);
		border: var(--border-hair) solid var(--color-border);
		border-radius: var(--radius-md) var(--radius-md) 0 0;
		background: var(--color-surface-muted);
		color: var(--color-text-muted);
		font-size: var(--text-sm);
		font-weight: var(--weight-semibold);
		white-space: nowrap;
		cursor: pointer;
	}

	.tab.on {
		background: var(--color-surface);
		border-bottom-color: var(--color-surface);
		color: var(--color-text);
	}
</style>
