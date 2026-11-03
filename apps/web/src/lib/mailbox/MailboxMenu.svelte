<script lang="ts">
	import type { Mailbox } from '#lib/api/client.js';
	import { Icon } from '#lib/ui/index.js';
	import { ago } from './mailbox';

	// The mailbox the inbox reads from, beside the business menu: always says whether mail is
	// flowing, so a broken connection is never silent.
	let {
		mailbox,
		busy = false,
		onsync,
		onpause,
		onresume,
		ondisconnect,
		onreconnect
	}: {
		mailbox: Mailbox;
		busy?: boolean;
		onsync: () => void;
		onpause: () => void;
		onresume: () => void;
		ondisconnect: () => void;
		onreconnect: () => void;
	} = $props();

	let open = $state(false);
	let root = $state<HTMLElement>();

	const synced = $derived(ago(mailbox.last_synced_at));
	const summary = $derived(
		mailbox.status === 'needs_reauth'
			? 'Reconnect'
			: mailbox.status === 'paused'
				? 'Paused'
				: (synced ?? 'reading')
	);

	function run(action: () => void) {
		open = false;
		action();
	}

	function onclick(event: MouseEvent) {
		if (open && !root?.contains(event.target as Node)) open = false;
	}

	function onkeydown(event: KeyboardEvent) {
		if (open && event.key === 'Escape') open = false;
	}

	const item =
		'flex min-h-10 w-full cursor-pointer items-center gap-2.5 rounded-sm px-2.5 text-left text-md hover:bg-subtle disabled:cursor-not-allowed disabled:text-muted';
</script>

<svelte:window {onclick} {onkeydown} />

<div bind:this={root} class="relative">
	{#if mailbox.status === 'needs_reauth'}
		<!-- Broken: one click reconnects, no menu in the way. -->
		<button
			type="button"
			class="inline-flex h-control-md cursor-pointer items-center gap-2 rounded-sm border border-danger-fg bg-danger-bg px-2.5 text-sm font-semibold text-danger-fg"
			disabled={busy}
			onclick={onreconnect}
		>
			<Icon name="alert" size={16} />{mailbox.email_address}<span class="font-bold">Reconnect</span>
		</button>
	{:else}
		<button
			type="button"
			aria-haspopup="true"
			aria-expanded={open}
			class="inline-flex h-control-md cursor-pointer items-center gap-2 rounded-sm border border-control bg-surface px-2.5 text-sm font-semibold"
			onclick={() => (open = !open)}
		>
			<span
				class={['size-2 rounded-full', mailbox.status === 'active' ? 'bg-live' : 'bg-line-strong']}
			></span>
			{mailbox.email_address}
			<span class="font-medium text-muted">{summary}</span>
			<Icon name="down" size={16} />
		</button>
	{/if}
	{#if open}
		<div
			class="absolute top-full right-0 z-10 mt-1.5 flex w-80 flex-col rounded-lg border border-line-strong bg-surface p-1.5 shadow-popover"
		>
			<div class="px-2.5 pt-2 pb-2.5">
				<p class="font-bold">{mailbox.email_address}</p>
				<p class="text-sm text-muted">
					Gmail · {mailbox.status === 'paused' ? 'paused, mail waits' : 'live'}{synced
						? ` · checked ${synced}`
						: ''}
				</p>
			</div>
			<hr class="mx-1 mb-1.5 border-t border-dashed border-line-dashed" />
			{#if mailbox.status === 'paused'}
				<button type="button" class={item} disabled={busy} onclick={() => run(onresume)}>
					<Icon name="play" size={16} />Resume
				</button>
			{:else}
				<button type="button" class={item} disabled={busy} onclick={() => run(onsync)}>
					<Icon name="redo" size={16} />Check for new mail now
				</button>
				<button type="button" class={item} disabled={busy} onclick={() => run(onpause)}>
					<Icon name="pause" size={16} /><span class="flex-1">Pause</span>
					<span class="text-sm text-muted">mail waits</span>
				</button>
			{/if}
			<button type="button" class={item} disabled={busy} onclick={() => run(ondisconnect)}>
				<Icon name="close" size={16} />Disconnect
			</button>
		</div>
	{/if}
</div>
