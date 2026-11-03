<script lang="ts">
	import { resolve } from '$app/paths';
	import type { Workspace } from '#lib/api/client.js';
	import { Icon } from '#lib/ui/index.js';

	// Switch business, finish a draft, or add one. Drafts take no email, so they open setup
	// instead of the inbox.
	let { workspaces, selected = $bindable() }: { workspaces: Workspace[]; selected: string | null } =
		$props();

	let open = $state(false);
	let root = $state<HTMLElement>();

	const ready = $derived(workspaces.filter((w) => w.setup_done));
	const drafts = $derived(workspaces.filter((w) => !w.setup_done));
	const current = $derived(ready.find((w) => w.id === selected));

	function choose(id: string) {
		selected = id;
		open = false;
	}

	function onclick(event: MouseEvent) {
		if (open && !root?.contains(event.target as Node)) open = false;
	}

	function onkeydown(event: KeyboardEvent) {
		if (open && event.key === 'Escape') open = false;
	}
</script>

<svelte:window {onclick} {onkeydown} />

<div bind:this={root} class="relative">
	<button
		type="button"
		aria-haspopup="true"
		aria-expanded={open}
		class="inline-flex h-control-md cursor-pointer items-center gap-2 rounded-sm border border-control bg-surface px-2.5 text-sm font-semibold"
		onclick={() => (open = !open)}
	>
		{current?.name ?? 'Businesses'}
		<Icon name="down" size={16} />
	</button>
	{#if open}
		<div
			class="absolute top-full right-0 z-10 mt-1.5 flex w-75 flex-col rounded-lg border border-line-strong bg-surface p-1.5 shadow-popover"
		>
			{#each ready as w (w.id)}
				<button
					type="button"
					aria-current={w.id === selected ? 'true' : undefined}
					class={[
						'flex min-h-10 cursor-pointer items-center gap-2.5 rounded-sm px-2.5 text-left text-md hover:bg-subtle',
						w.id === selected && 'bg-subtle font-semibold'
					]}
					onclick={() => choose(w.id)}
				>
					<span class="flex-1">{w.name}</span>
					{#if w.id === selected}<Icon name="check" size={16} />{/if}
				</button>
			{/each}
			{#each drafts as w (w.id)}
				<a
					href={resolve('/setup/[[workspace]]', { workspace: w.id })}
					class="flex min-h-10 items-center gap-2.5 rounded-sm px-2.5 text-md hover:bg-subtle"
				>
					<span class="rounded-xs bg-warning-bg px-1.5 text-xs font-bold text-warning-fg"
						>Draft</span
					>
					<span class="flex-1">{w.name}</span>
					<span class="text-sm font-bold">Finish setup</span>
				</a>
			{/each}
			<hr class="mx-1 my-1.5 border-t border-dashed border-line-dashed" />
			<a
				href={resolve('/setup/[[workspace]]', {})}
				class="flex min-h-10 items-center gap-2.5 rounded-sm px-2.5 text-md hover:bg-subtle"
			>
				<Icon name="plus" size={16} />Add a business
			</a>
		</div>
	{/if}
</div>
