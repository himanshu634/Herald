<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon, { type IconName } from './Icon.svelte';
	import type { Tone } from './tones';

	let {
		tone = 'neutral',
		icon,
		children
	}: { tone?: Tone; icon?: IconName; children: Snippet } = $props();
</script>

<span class={['tag', tone]}>
	{#if icon}<Icon name={icon} size={11} />{/if}
	{@render children()}
</span>

<style>
	.tag {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		height: 1.25rem;
		padding: 0 0.375rem;
		border-radius: var(--radius-xs);
		font-size: var(--text-xs);
		font-weight: var(--weight-semibold);
		line-height: 1;
		white-space: nowrap;
	}

	.danger {
		background: var(--tone-danger-bg);
		color: var(--tone-danger-fg);
	}
	.warning {
		background: var(--tone-warning-bg);
		color: var(--tone-warning-fg);
	}
	.success {
		background: var(--tone-success-bg);
		color: var(--tone-success-fg);
	}
	.neutral {
		background: var(--tone-neutral-bg);
		color: var(--tone-neutral-fg);
	}
	.muted {
		background: var(--tone-muted-bg);
		color: var(--tone-muted-fg);
	}
	.floor {
		background: var(--tone-floor-bg);
		color: var(--tone-floor-fg);
	}
	.accent {
		background: var(--color-accent-tint);
		color: var(--color-text);
	}
</style>
