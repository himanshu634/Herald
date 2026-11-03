<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';

	let {
		label,
		children
	}: {
		/** The trigger's text, such as a panel title. */
		label: string;
		children: Snippet;
	} = $props();

	const id = $props.id();
	let open = $state(false);
	let closing: ReturnType<typeof setTimeout> | undefined;

	function show() {
		clearTimeout(closing);
		open = true;
	}

	// A short delay lets the pointer cross the gap from the trigger into the card without it
	// closing, so the owner can keep it open while they read (WCAG 1.4.13, hoverable).
	function hide() {
		clearTimeout(closing);
		closing = setTimeout(() => (open = false), 120);
	}

	// Escape closes it without moving the pointer or focus (WCAG 1.4.13, dismissible). It listens
	// on the window because a card opened by hover has no focus inside it.
	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && open) open = false;
	}
</script>

<svelte:window {onkeydown} />

<!-- Touch fires pointerleave as the finger lifts, which would close a card just tapped open,
	so only a mouse or pen opens and closes it by hovering. A tap goes through focus and click. -->
<span
	class="relative inline-flex"
	role="presentation"
	onpointerenter={(e) => e.pointerType !== 'touch' && show()}
	onpointerleave={(e) => e.pointerType !== 'touch' && hide()}
>
	<!-- A button, so keyboard users reach it and a tap opens it where there is no hover. -->
	<button
		type="button"
		class="inline-flex cursor-help items-center gap-1.5 rounded-xs text-left underline decoration-line-strong decoration-dotted underline-offset-4"
		aria-describedby={id}
		onfocus={show}
		onblur={hide}
		onclick={show}
	>
		{label}<span class="text-muted"><Icon name="info" size={14} /></span>
	</button>
	<!-- Kept in the DOM while closed so aria-describedby always has text to read. On a phone the
		card is narrowed by the rail and gutters left of a panel title (7rem), so it stays on screen. -->
	<div
		{id}
		role="tooltip"
		class={[
			'absolute top-full left-0 z-20 w-[min(20rem,calc(100vw-7rem))] pt-2',
			open ? 'block' : 'hidden'
		]}
	>
		<div
			class="rounded-lg border border-line-strong bg-surface p-3.5 text-sm font-normal text-body shadow-popover"
		>
			{@render children()}
		</div>
	</div>
</span>
