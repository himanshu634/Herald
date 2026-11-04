<script lang="ts">
	import { cubicIn, cubicOut } from 'svelte/easing';
	import { prefersReducedMotion } from 'svelte/motion';
	import { fly } from 'svelte/transition';

	let { message, ondismiss }: { message: string | null; ondismiss: () => void } = $props();

	// Svelte transitions run on the Web Animations API, which the reduced-motion rule in app.css
	// does not reach, so they check the setting themselves.
	const still = $derived(prefersReducedMotion.current);
</script>

<!-- Top centre: the owner's next press is in the action bar at the bottom, so the toast must
	not cover it. The live region stays in the DOM so screen readers hear each new message. -->
<div class="pointer-events-none fixed inset-x-0 top-3 z-50 flex justify-center px-4">
	<div role="status" aria-live="polite">
		{#if message}
			<div
				in:fly={{ y: still ? 0 : -16, duration: still ? 0 : 220, easing: cubicOut }}
				out:fly={{ y: still ? 0 : -8, duration: still ? 0 : 150, easing: cubicIn }}
				class="pointer-events-auto flex items-center gap-3 rounded-lg bg-ink py-2 pr-2 pl-4 text-md text-canvas shadow-popover"
			>
				<p>{message}</p>
				<button
					type="button"
					class="h-control-sm cursor-pointer rounded-sm px-2 text-sm font-bold text-accent"
					onclick={ondismiss}>Dismiss</button
				>
			</div>
		{/if}
	</div>
</div>
