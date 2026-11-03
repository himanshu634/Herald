<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import Kbd from './Kbd.svelte';

	let {
		variant = 'secondary',
		size = 'md',
		kbd,
		type = 'button',
		children,
		...rest
	}: HTMLButtonAttributes & {
		/** primary: the one main action in a view. secondary: every other action. quiet: low-stakes, no base. */
		variant?: 'primary' | 'secondary' | 'quiet';
		size?: 'sm' | 'md';
		/** Shortcut shown on the button. Wire the key yourself; this only displays it. */
		kbd?: string;
		children: Snippet;
	} = $props();
</script>

<button {type} class={['press', variant, size]} aria-keyshortcuts={kbd} {...rest}>
	<span class="face">
		{@render children()}
		{#if kbd}<Kbd>{kbd}</Kbd>{/if}
	</span>
</button>

<style>
	.press {
		display: inline-block;
		padding: 0;
		border: var(--border-press) solid var(--color-press-edge);
		border-radius: var(--radius-md);
		background: var(--color-press-base);
		cursor: pointer;
	}

	.face {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-2);
		/* The border sits outside the base; pull the face up so the edges line up. */
		margin: calc(var(--border-press) * -1);
		padding: 0.4375rem var(--space-4);
		border: var(--border-press) solid var(--color-press-edge);
		border-radius: var(--radius-md);
		background: var(--color-press-face);
		color: var(--color-text);
		font-size: var(--text-md);
		font-weight: var(--weight-bold);
		line-height: var(--leading-tight);
		white-space: nowrap;
		transform: translateY(calc(var(--press-depth) * -1));
		/* Snappy in, eased out: no transition on hover, only on release. */
		transition: transform var(--duration-base) var(--ease-out);
	}

	.press:active .face {
		transform: translateY(calc(var(--press-depth-active) * -1));
		transition: none;
	}

	.primary {
		border-color: var(--color-accent-edge);
		background: var(--color-accent-base);
	}

	.primary .face {
		border-color: var(--color-accent-edge);
		background: var(--color-accent);
		color: var(--color-on-accent);
	}

	.quiet {
		border-color: transparent;
		background: transparent;
	}

	.quiet .face {
		border-color: transparent;
		background: transparent;
		transform: none;
	}

	.quiet:hover .face {
		background: var(--color-surface-muted);
	}

	.sm .face {
		padding: 0.3125rem var(--space-3);
		font-size: var(--text-sm);
	}

	.press:focus-visible {
		outline: 2px solid var(--color-focus);
		outline-offset: 3px;
	}

	.press:disabled {
		cursor: not-allowed;
		opacity: 0.5;
	}

	.press:disabled .face {
		transform: none;
	}
</style>
