<script lang="ts">
	import { angerLabel } from './tones';

	let { level, showLabel = false }: { level: number; showLabel?: boolean } = $props();

	const label = $derived(angerLabel(level));
	const filled = $derived(Math.min(5, Math.max(1, Math.round(level))));
</script>

<span class="anger" role="img" aria-label={label}>
	{#each [1, 2, 3, 4, 5] as step (step)}
		<span class={['bar', step <= filled && 'on']}></span>
	{/each}
	{#if showLabel}<span class="text" aria-hidden="true">{label.replace(' of 5,', ',')}</span>{/if}
</span>

<style>
	.anger {
		display: inline-flex;
		align-items: center;
		gap: 2px;
	}

	.bar {
		width: 5px;
		height: 12px;
		border-radius: 2px;
		background: var(--anger-off);
	}

	.bar.on {
		background: var(--anger-on);
	}

	.text {
		margin-left: var(--space-2);
		font-size: var(--text-sm);
	}
</style>
