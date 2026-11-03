<script lang="ts">
	import type { Snippet } from 'svelte';
	import { Icon, TONE_CLASSES } from '#lib/ui/index.js';
	import type { Look } from './reply';

	// One state line for a reply: can't reply, sending, sent, not sent, not confirmed.
	let {
		look,
		text,
		alert = false,
		children
	}: {
		look: Look;
		text: string;
		/** Read out at once: the owner's send just failed. */
		alert?: boolean;
		/** An action under the words, like Reconnect Gmail. */
		children?: Snippet;
	} = $props();
</script>

<div
	role={alert ? 'alert' : undefined}
	class={['flex items-start gap-2.5 rounded-md px-3 py-2.5 text-sm', TONE_CLASSES[look.tone]]}
>
	<span class="mt-px"><Icon name={look.icon} size={16} /></span>
	<div class="flex min-w-0 flex-col gap-2">
		<p>{text}</p>
		{#if children}<div class="flex flex-wrap gap-2">{@render children()}</div>{/if}
	</div>
</div>
