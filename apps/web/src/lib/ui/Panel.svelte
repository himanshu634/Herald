<script lang="ts">
	import type { Snippet } from 'svelte';
	import HoverCard from './HoverCard.svelte';

	let {
		title,
		info,
		actions,
		padded = true,
		class: className,
		children
	}: {
		title?: string;
		/** What this panel is for, shown in a hover card on the title. Needs a title. */
		info?: Snippet;
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
			{#if title}
				<h2 class="text-md font-bold">
					{#if info}<HoverCard label={title}>{@render info()}</HoverCard>{:else}{title}{/if}
				</h2>
			{/if}
			{#if actions}<div class="flex gap-2">{@render actions()}</div>{/if}
		</header>
	{/if}
	<div class={padded ? 'p-4' : undefined}>{@render children()}</div>
</section>
