<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import Kbd from './Kbd.svelte';

	let {
		variant = 'secondary',
		size = 'md',
		kbd,
		type = 'button',
		class: className,
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

	// The base sits under the face; the face is raised by --press-depth and drops on click.
	const BASE = {
		primary: 'border-accent-edge bg-accent-base',
		secondary: 'border-press-edge bg-press-base',
		quiet: 'border-transparent bg-transparent'
	};
	const FACE = {
		primary: 'border-accent-edge bg-accent text-on-accent',
		secondary: 'border-press-edge bg-press-face text-ink',
		quiet: 'translate-y-0! border-transparent bg-transparent text-ink group-hover:bg-subtle'
	};
	const SIZE = { sm: 'px-3 py-1.25 text-sm', md: 'px-4 py-1.75 text-md' };
</script>

<button
	{type}
	class={[
		'group inline-block cursor-pointer rounded-md border-[1.5px] p-0 focus-visible:outline-offset-3 disabled:cursor-not-allowed disabled:opacity-50',
		BASE[variant],
		className
	]}
	aria-keyshortcuts={kbd}
	{...rest}
>
	<span
		class={[
			'-m-[1.5px] flex -translate-y-(--press-depth) items-center justify-center gap-2 rounded-md border-[1.5px] leading-tight font-bold whitespace-nowrap',
			// Snappy in, eased out: nothing moves on hover, the face eases back after a click.
			'transition-transform duration-160 ease-out group-active:-translate-y-(--press-depth-active) group-active:transition-none group-disabled:translate-y-0',
			FACE[variant],
			SIZE[size]
		]}
	>
		{@render children()}
		{#if kbd}<Kbd>{kbd}</Kbd>{/if}
	</span>
</button>
