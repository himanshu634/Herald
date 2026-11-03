<script lang="ts">
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();
</script>

<kbd>{@render children()}</kbd>

<style>
	kbd {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 1.125rem;
		height: 1.125rem;
		padding: 0 var(--space-1);
		border: var(--border-hair) solid color-mix(in srgb, currentColor 35%, transparent);
		border-radius: var(--radius-xs);
		font-family: inherit;
		font-size: 0.6875rem;
		font-weight: var(--weight-bold);
		line-height: 1;
	}
</style>
