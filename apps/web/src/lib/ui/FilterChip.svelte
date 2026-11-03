<script lang="ts">
	import type { Snippet } from 'svelte';

	let { pressed = $bindable(false), children }: { pressed?: boolean; children: Snippet } = $props();
</script>

<button
	type="button"
	class={['chip', pressed && 'on']}
	aria-pressed={pressed}
	onclick={() => (pressed = !pressed)}
>
	{@render children()}
</button>

<style>
	.chip {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		height: var(--control-md);
		padding: 0 0.625rem;
		border: var(--border-hair) dashed var(--color-border-control);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		color: var(--tone-neutral-fg);
		font-size: var(--text-sm);
		font-weight: var(--weight-semibold);
		white-space: nowrap;
		cursor: pointer;
	}

	.chip.on {
		border-style: solid;
		border-color: var(--color-text);
		color: var(--color-text);
	}
</style>
