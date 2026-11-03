<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		title,
		actions,
		padded = true,
		class: className,
		children
	}: {
		title?: string;
		actions?: Snippet;
		/** Turn off for edge-to-edge content such as a table. */
		padded?: boolean;
		class?: string;
		children: Snippet;
	} = $props();
</script>

<section class={['min-w-0 rounded-lg border border-line bg-surface', className]} aria-label={title}>
	{#if title || actions}
		<header
			class="flex items-center justify-between gap-3 border-b border-dashed border-line-dashed px-4 py-3"
		>
			{#if title}<h2 class="text-md font-bold">{title}</h2>{/if}
			{#if actions}<div class="flex gap-2">{@render actions()}</div>{/if}
		</header>
	{/if}
	<div class={padded ? 'p-4' : undefined}>{@render children()}</div>
</section>
