<script lang="ts">
	import type { Snippet } from 'svelte';

	let { title, actions, children }: { title?: string; actions?: Snippet; children: Snippet } =
		$props();
</script>

<section class="panel" aria-label={title}>
	{#if title || actions}
		<header>
			{#if title}<h2>{title}</h2>{/if}
			{#if actions}<div class="actions">{@render actions()}</div>{/if}
		</header>
	{/if}
	<div class="body">{@render children()}</div>
</section>

<style>
	.panel {
		background: var(--color-surface);
		border: var(--border-hair) solid var(--color-border);
		border-radius: var(--radius-lg);
		min-width: 0;
	}

	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-3);
		padding: var(--space-3) var(--space-4);
		border-bottom: var(--border-hair) dashed var(--color-border-dashed);
	}

	h2 {
		font-size: var(--text-md);
		font-weight: var(--weight-bold);
	}

	.actions {
		display: flex;
		gap: var(--space-2);
	}

	.body {
		padding: var(--space-4);
	}
</style>
