<script lang="ts">
	import { resolve } from '$app/paths';
	import { prefs } from '#lib/prefs.svelte.js';
	import { Icon, Logo, ThemeSwitch, type IconName } from '#lib/ui/index.js';

	type Desk = 'alerts' | 'inbox';

	let {
		current = null,
		alerts = 0,
		workspace = '',
		onpick
	}: {
		/** Which desk the page shows; null on pages that are neither (setup). */
		current?: Desk | null;
		/** Open alerts, shown as a badge on Alerts. */
		alerts?: number;
		/** The business on screen, so the links don't fall back to the first one. */
		workspace?: string;
		/** The page switches desks itself (keeps its state); otherwise the links navigate. */
		onpick?: (desk: Desk) => void;
	} = $props();

	// The main nav on every app screen. Collapsed it is the 56 px icon rail; open it adds labels.
	// Every item keeps the same 40 px icon column in both states, so icons stay put while the
	// width animates and the labels are simply clipped.
	const open = $derived(prefs.railOpen);

	const DESKS: { id: Desk; label: string; icon: IconName }[] = [
		{ id: 'alerts', label: 'Alerts', icon: 'bell' },
		{ id: 'inbox', label: 'Inbox', icon: 'inbox' }
	];

	// Alerts is the app's default view, so its link needs no view; the inbox opens on its first tab.
	function href(desk: Desk): string {
		const query = [
			workspace && `workspace=${encodeURIComponent(workspace)}`,
			desk === 'inbox' && 'view=needs-a-look'
		].filter(Boolean);
		return `${resolve('/')}${query.length ? `?${query.join('&')}` : ''}`;
	}

	function pick(event: MouseEvent, desk: Desk) {
		// A plain click stays in the page; a modified one opens a tab the usual way.
		if (!onpick || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
		event.preventDefault();
		onpick(desk);
	}

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
			><Logo size={34} label={open ? undefined : 'Herald'} /></span
		>
		{#if open}<span class="text-lg font-extrabold tracking-display">Herald</span>{/if}
	</a>

	{#each DESKS as desk (desk.id)}
		{@const badge = desk.id === 'alerts' && alerts > 0 ? alerts : null}
		{@const name = badge ? `${desk.label}, ${badge} open` : desk.label}
		<!-- The href is built with resolve('/') above; the rule can't see through the query. -->
		<!-- eslint-disable svelte/no-navigation-without-resolve -->
		<a
			href={href(desk.id)}
			aria-current={current === desk.id ? 'page' : undefined}
			aria-label={open ? undefined : name}
			title={open ? undefined : name}
			class={[
				item,
				'relative font-semibold text-ink no-underline',
				current === desk.id ? 'border border-line bg-surface' : 'hover:bg-subtle'
			]}
			onclick={(event) => pick(event, desk.id)}
		>
			<Icon name={desk.icon} />
			{#if open}<span class="flex-1">{desk.label}</span>{/if}
			{#if badge}
				<span
					class={[
						'flex h-4.5 min-w-4.5 items-center justify-center rounded-full bg-danger-fg px-1 text-xs font-extrabold text-surface',
						!open && 'absolute top-0.5 right-0.5'
					]}>{badge}</span
				>
			{/if}
		</a>
		<!-- eslint-enable svelte/no-navigation-without-resolve -->
	{/each}
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
