<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { prefs } from '#lib/prefs.svelte.js';
	import { Icon, Logo, ThemeSwitch } from '#lib/ui/index.js';

	// The main nav on every app screen. Collapsed it is the 56 px icon rail; open it adds labels.
	// Every item keeps the same 40 px icon column in both states, so icons stay put while the
	// width animates and the labels are simply clipped.
	const open = $derived(prefs.railOpen);
	const onInbox = $derived(page.url.pathname === resolve('/'));

	const SOON = [
		['rules', 'Rules'],
		['business', 'Business profile'],
		['chart', 'Score report']
	] as const;

	const item =
		'flex h-control-lg w-full items-center gap-2.5 overflow-hidden rounded-md px-2.5 text-md whitespace-nowrap';
</script>

<nav
	id="main-rail"
	aria-label="Main"
	class={[
		'sticky top-0 flex h-screen flex-none flex-col gap-1.5 overflow-hidden border-r border-line bg-sunken px-2 py-3 transition-[width] duration-200 ease-out',
		open ? 'w-rail-wide' : 'w-rail'
	]}
>
	<a
		href={resolve('/')}
		class="mb-2.5 flex items-center gap-2.5 overflow-hidden whitespace-nowrap text-ink no-underline"
	>
		<span class="flex size-control-lg flex-none items-center justify-center"
			><Logo size={34} label={open ? undefined : 'Herald inbox'} /></span
		>
		{#if open}<span class="text-lg font-extrabold tracking-display">Herald</span>{/if}
	</a>

	<a
		href={resolve('/')}
		aria-current={onInbox ? 'page' : undefined}
		aria-label={open ? undefined : 'Inbox'}
		title={open ? undefined : 'Inbox'}
		class={[
			item,
			'font-semibold text-ink no-underline',
			onInbox ? 'border border-line bg-surface' : 'hover:bg-subtle'
		]}
		><Icon name="inbox" />{#if open}Inbox{/if}</a
	>
	{#each SOON as [icon, name] (icon)}
		<button
			type="button"
			disabled
			aria-label={`${name}, coming soon`}
			title={`${name}, coming soon`}
			class={[item, 'cursor-not-allowed text-muted']}
		>
			<Icon name={icon} />
			{#if open}<span class="flex-1 text-left">{name}</span><span class="text-xs">Soon</span>{/if}
		</button>
	{/each}

	<div class={['mt-auto flex flex-col gap-1.5', !open && 'items-center']}>
		{#if open}
			<span class="px-2.5 text-xs font-bold text-muted">Theme</span>
			<span class="px-1"><ThemeSwitch /></span>
		{:else}
			<ThemeSwitch vertical />
		{/if}
		<button
			type="button"
			aria-controls="main-rail"
			aria-expanded={open}
			aria-label={open ? undefined : 'Expand sidebar'}
			title={open ? undefined : 'Expand sidebar'}
			class={[item, 'cursor-pointer text-muted hover:bg-subtle hover:text-ink']}
			onclick={() => prefs.toggleRail()}
		>
			<Icon name="sidebar" />{#if open}Collapse sidebar{/if}
		</button>
	</div>
</nav>
