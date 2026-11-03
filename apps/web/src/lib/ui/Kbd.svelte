<script lang="ts">
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();
</script>

<kbd
	class="inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-xs border border-current/35 px-1 font-sans text-[0.6875rem] leading-none font-bold"
	>{@render children()}</kbd
>
