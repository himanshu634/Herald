<script lang="ts">
	import { angerLabel } from './tones';

	let { level, showLabel = false }: { level: number; showLabel?: boolean } = $props();

	const label = $derived(angerLabel(level));
	const filled = $derived(Math.min(5, Math.max(1, Math.round(level))));
</script>

<span class="inline-flex items-center gap-0.5" role="img" aria-label={label}>
	{#each [1, 2, 3, 4, 5] as step (step)}
		<span class={['h-3 w-1.25 rounded-[2px]', step <= filled ? 'bg-anger-on' : 'bg-anger-off']}
		></span>
	{/each}
	{#if showLabel}
		<span class="ml-2 text-sm" aria-hidden="true">{label.replace(' of 5,', ',')}</span>
	{/if}
</span>
