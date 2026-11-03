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

<div
	class="flex gap-1 overflow-x-auto border-b border-line"
	role="tablist"
	aria-label={label}
	tabindex="-1"
	{onkeydown}
>
	{#each items as item (item.id)}
		<button
			type="button"
			role="tab"
			data-tab={item.id}
			class={[
				'-mb-px inline-flex h-tab cursor-pointer items-center gap-2 rounded-t-md border border-line px-3 text-sm font-semibold whitespace-nowrap',
				item.id === current ? 'border-b-surface bg-surface text-ink' : 'bg-subtle text-muted'
			]}
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
