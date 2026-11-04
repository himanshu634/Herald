<script lang="ts">
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();
</script>

<!-- Hidden on touch screens: there is no keyboard, and the keys would push buttons onto a second row. -->
<kbd
	class="inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-xs border border-current/35 px-1 font-mono text-[0.6875rem] leading-none font-bold pointer-coarse:hidden"
	>{@render children()}</kbd
>
