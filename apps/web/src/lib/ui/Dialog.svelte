<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';

	let {
		open,
		label,
		onclose,
		header,
		children,
		footer
	}: {
		open: boolean;
		/** The dialog's accessible name. */
		label: string;
		/** Esc, the close button and a click on the backdrop all call this. */
		onclose: () => void;
		header: Snippet;
		children: Snippet;
		footer?: Snippet;
	} = $props();

	let dialog = $state<HTMLDialogElement>();

	// showModal() is what makes it modal: focus moves in and stays, the page behind goes inert,
	// and Esc fires "close". Only the DOM can do that, so this effect syncs `open` to it.
	$effect(() => {
		if (!dialog) return;
		if (open && !dialog.open) dialog.showModal();
		if (!open && dialog.open) dialog.close();
	});
</script>

<!-- 80% of the window, full screen on a phone. A click lands on the dialog element itself
	only on its backdrop, since the content fills it edge to edge. -->
<dialog
	bind:this={dialog}
	aria-label={label}
	{onclose}
	onclick={(event) => event.target === dialog && onclose()}
	class="m-auto h-[80vh] max-h-none w-[80vw] max-w-none flex-col overflow-hidden rounded-xl border border-line-strong bg-surface p-0 text-ink shadow-popover backdrop:bg-[rgb(0_0_0/0.5)] open:flex max-md:h-dvh max-md:w-screen max-md:rounded-none"
>
	<header
		class="flex flex-none items-start justify-between gap-4 border-b border-dashed border-line-dashed px-5 py-4"
	>
		<div class="min-w-0 flex-1">{@render header()}</div>
		<button
			type="button"
			class="inline-flex size-control-md flex-none cursor-pointer items-center justify-center rounded-sm border border-line text-neutral-fg hover:bg-subtle"
			aria-label="Close"
			onclick={onclose}><Icon name="close" size={16} /></button
		>
	</header>
	<div class="flex min-h-0 flex-1 flex-col max-md:overflow-y-auto md:flex-row">
		{@render children()}
	</div>
	{#if footer}
		<footer
			class="flex flex-none flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-3"
		>
			{@render footer()}
		</footer>
	{/if}
</dialog>
