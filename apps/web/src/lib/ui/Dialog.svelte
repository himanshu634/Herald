<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';

	let {
		open,
		label,
		onclose,
		header,
		children,
		footer,
		aside,
		onescape
	}: {
		open: boolean;
		/** The dialog's accessible name. */
		label: string;
		/** Esc, the close button and a click on the backdrop all call this. */
		onclose: () => void;
		header: Snippet;
		children: Snippet;
		footer?: Snippet;
		/** A side panel docked to the right edge. The dialog widens to make room for it. */
		aside?: Snippet;
		/** Esc goes here first. Return true when it closed something inside, like the side panel. */
		onescape?: () => boolean;
	} = $props();

	let dialog = $state<HTMLDialogElement>();
	// Where the last press started. A text selection dragged from a field out onto the backdrop
	// ends with a click on the dialog element, which must not close it and lose the typing.
	let pressedOn: EventTarget | null = null;

	// showModal() is what makes it modal: focus moves in and stays, the page behind goes inert,
	// and Esc fires "close". Only the DOM can do that, so this effect syncs `open` to it.
	$effect(() => {
		if (!dialog) return;
		if (open && !dialog.open) dialog.showModal();
		if (!open && dialog.open) dialog.close();
	});

	// The browser can close the dialog itself: Chrome skips "cancel" on a repeated Esc with no
	// click in between, so onescape never gets the chance to keep it. The parent may still want
	// it open (say, to ask about unsaved changes); then the effect above won't rerun, as `open`
	// never changed, so reopen it here once the parent has had its say.
	function closed() {
		onclose();
		queueMicrotask(() => {
			if (open && dialog && !dialog.open) dialog.showModal();
		});
	}
</script>

<!-- 80% of the window, full screen on a phone. A press lands on the dialog element itself
	only on its backdrop, since the content fills it edge to edge. -->
<dialog
	bind:this={dialog}
	aria-label={label}
	onclose={closed}
	oncancel={(event) => onescape?.() && event.preventDefault()}
	onpointerdown={(event) => (pressedOn = event.target)}
	onclick={(event) => event.target === dialog && pressedOn === dialog && onclose()}
	class={[
		'm-auto h-[80vh] max-h-none max-w-none overflow-hidden rounded-xl border border-line-strong bg-surface p-0 text-ink shadow-popover transition-[width] duration-200 ease-out backdrop:bg-[rgb(0_0_0/0.5)] open:flex motion-reduce:transition-none max-md:h-dvh max-md:w-screen max-md:rounded-none',
		aside ? 'w-[min(96vw,calc(80vw+26rem))]' : 'w-[80vw]'
	]}
>
	<div class="flex min-w-0 flex-1 flex-col">
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
	</div>
	{#if aside}
		<!-- Beside the dialog's own columns from md, so the email stays readable while editing;
			over them on a phone, where there is no room beside. -->
		<div
			class="flex w-[26rem] flex-none flex-col border-l-[1.5px] border-ink bg-surface max-md:absolute max-md:inset-0 max-md:w-auto max-md:border-l-0"
		>
			{@render aside()}
		</div>
	{/if}
</dialog>
