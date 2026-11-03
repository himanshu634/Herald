<script lang="ts">
	import type { Snippet } from 'svelte';

	let { pressed = $bindable(false), children }: { pressed?: boolean; children: Snippet } = $props();
</script>

<button
	type="button"
	class={[
		'inline-flex h-control-md cursor-pointer items-center gap-2 rounded-sm border bg-surface px-2.5 text-sm font-semibold whitespace-nowrap',
		pressed ? 'border-solid border-ink text-ink' : 'border-dashed border-control text-neutral-fg'
	]}
	aria-pressed={pressed}
	onclick={() => (pressed = !pressed)}
>
	{@render children()}
</button>
