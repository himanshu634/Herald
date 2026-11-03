<script lang="ts">
	import { resolve } from '$app/paths';
	import { api, type Email, type EmailIn, type Workspace } from '#lib/api/client.js';
	import { WorkspaceEvents } from '#lib/events.svelte.js';
	import EmailPanel from '#lib/inbox/EmailPanel.svelte';
	import EmailTable from '#lib/inbox/EmailTable.svelte';
	import SendTestEmail from '#lib/inbox/SendTestEmail.svelte';
	import {
		ACTIONS,
		EMPTY,
		VIEWS,
		actionsFor,
		countByView,
		visibleEmails,
		type Action,
		type Filters,
		type ViewId
	} from '#lib/inbox/inbox.js';
	import { Button, FilterChip, Icon, Logo, Tabs, Toast, type TabItem } from '#lib/ui/index.js';

	let workspaces = $state.raw<Workspace[]>([]);
	let workspaceId = $state<string | null>(null);
	let emails = $state.raw<Email[]>([]);
	let loaded = $state(false);
	let error = $state<string | null>(null);
	let toast = $state<string | null>(null);
	let busy = $state(false);

	let view = $state<ViewId>('needs-you');
	let filters = $state<Filters>({ query: '', urgentOnly: false, angry: false, unsure: false });
	let chosenId = $state<string | null>(null);

	let search = $state<HTMLInputElement>();
	let sender = $state<SendTestEmail>();

	const live = new WorkspaceEvents();
	const workspace = $derived(workspaces.find((w) => w.id === workspaceId));
	const counts = $derived(countByView(emails));
	const visible = $derived(visibleEmails(emails, view, filters));
	// Keep the owner's choice while it is in view; otherwise open the top email.
	const selected = $derived(visible.find((e) => e.id === chosenId) ?? visible[0] ?? null);
	const tabs = $derived<TabItem[]>(
		VIEWS.map((v) => ({ id: v.id, label: v.label, count: counts[v.id], countTone: v.countTone }))
	);

	api
		.listWorkspaces()
		.then((list) => {
			workspaces = list;
			workspaceId = list[0]?.id ?? null;
			loaded = true;
		})
		.catch(fail);

	$effect(() => {
		if (!workspaceId) return;
		const id = workspaceId;
		refresh(id);
		live.connect(id);
		const stop = live.onEvent(() => refresh(id));
		return () => {
			stop();
			live.close();
		};
	});

	// Messages clear themselves after a few seconds.
	$effect(() => {
		if (!toast) return;
		const timer = setTimeout(() => (toast = null), 5000);
		return () => clearTimeout(timer);
	});

	function fail(e: unknown) {
		error = e instanceof Error ? e.message : String(e);
		loaded = true;
	}

	async function refresh(id: string) {
		try {
			emails = await api.listEmails(id);
		} catch (e) {
			fail(e);
		}
	}

	async function createDemo() {
		try {
			const created = await api.createDemoWorkspace();
			workspaces = [...workspaces, created];
			workspaceId = created.id;
		} catch (e) {
			fail(e);
		}
	}

	async function send(draft: EmailIn) {
		if (!workspaceId) return;
		try {
			await api.sendTestEmail(workspaceId, draft);
			toast = 'Sent. Herald is reading it now.';
			view = 'all';
		} catch (e) {
			fail(e);
		}
	}

	async function act(action: Action) {
		if (!selected || busy || !actionsFor(selected.status).includes(action)) return;
		busy = true;
		try {
			const updated = await api.act(selected.workspace_id, selected.id, action);
			emails = emails.map((e) => (e.id === updated.id ? updated : e));
			toast = ACTIONS[action].done;
		} catch (e) {
			fail(e);
		} finally {
			busy = false;
		}
	}

	function move(step: number) {
		if (!visible.length) return;
		const index = selected ? visible.indexOf(selected) : -1;
		chosenId = visible[Math.min(visible.length - 1, Math.max(0, index + step))].id;
	}

	// Owner shortcuts, from docs/design-system.md. Never while typing or in a dialog.
	function onkeydown(event: KeyboardEvent) {
		const target = event.target as HTMLElement;
		if (event.metaKey || event.ctrlKey || event.altKey) return;
		if (target.closest('input, textarea, select, dialog[open]')) return;
		const keys: Record<string, () => void> = {
			j: () => move(1),
			ArrowDown: () => move(1),
			k: () => move(-1),
			ArrowUp: () => move(-1),
			o: () => act('on-it'),
			n: () => act('not-urgent'),
			d: () => act('done'),
			'/': () => search?.focus()
		};
		const run = keys[event.key];
		if (!run) return;
		event.preventDefault();
		run();
	}
</script>

<svelte:window {onkeydown} />
<svelte:head><title>Inbox · Herald</title></svelte:head>

<div class="flex min-h-screen">
	<nav
		aria-label="Main"
		class="flex w-rail flex-none flex-col items-center gap-1.5 border-r border-line bg-sunken py-3"
	>
		<span class="mb-2.5"><Logo size={34} label="Herald" /></span>
		<a
			href={resolve('/')}
			aria-current="page"
			aria-label="Inbox"
			class="flex size-control-lg items-center justify-center rounded-md border border-line bg-surface"
			><Icon name="inbox" /></a
		>
		{#each [['rules', 'Rules'], ['business', 'Business profile'], ['chart', 'Score report']] as const as [icon, name] (icon)}
			<button
				type="button"
				disabled
				aria-label={`${name}, coming soon`}
				title={`${name}, coming soon`}
				class="flex size-control-lg cursor-not-allowed items-center justify-center rounded-md text-muted"
				><Icon name={icon} /></button
			>
		{/each}
	</nav>

	<div class="flex min-w-0 flex-1 flex-col">
		<header
			class="flex flex-wrap items-end justify-between gap-3 border-b border-line px-4 pt-2.5 lg:border-b-0"
		>
			{#if workspace}
				<Tabs items={tabs} bind:selected={view} label="Inbox views" />
			{:else}
				<h1 class="pb-2 text-2xl font-extrabold">Herald</h1>
			{/if}
			<div class="flex flex-wrap items-center gap-3 pb-1.5">
				{#if workspaces.length > 1}
					<select
						bind:value={workspaceId}
						aria-label="Workspace"
						class="h-control-md rounded-sm border border-control bg-surface px-2 text-sm"
					>
						{#each workspaces as w (w.id)}<option value={w.id}>{w.name}</option>{/each}
					</select>
				{/if}
				{#if workspace}
					<span class="inline-flex items-center gap-1.5 text-sm text-neutral-fg">
						<span class={['size-2 rounded-full', live.connected ? 'bg-live' : 'bg-line-strong']}
						></span>
						{workspace.name}, {live.connected ? 'live' : 'connecting'}
					</span>
					<Button onclick={() => sender?.open()}>Send test email</Button>
				{/if}
			</div>
		</header>

		{#if error}
			<div
				role="alert"
				class="mx-4 mt-3 flex items-center justify-between gap-3 rounded-lg bg-danger-bg px-4 py-2 text-sm text-danger-fg"
			>
				<p>Something went wrong: {error}</p>
				<Button variant="quiet" size="sm" onclick={() => (error = null)}>Dismiss</Button>
			</div>
		{/if}

		{#if workspace}
			<div class="flex flex-1 flex-col lg:flex-row">
				<main class="flex min-w-0 flex-1 flex-col gap-3 p-4 lg:border-t lg:border-line">
					<div class="flex flex-wrap items-center gap-2">
						<label class="sr-only" for="search">Search mail</label>
						<input
							id="search"
							bind:this={search}
							bind:value={filters.query}
							type="search"
							placeholder="Search mail  /"
							class="h-control-md w-56 rounded-sm border border-control bg-surface px-2.5 text-sm"
						/>
						<FilterChip bind:pressed={filters.urgentOnly}>Urgent</FilterChip>
						<FilterChip bind:pressed={filters.angry}>Anger 4+</FilterChip>
						<FilterChip bind:pressed={filters.unsure}>Herald unsure</FilterChip>
					</div>

					{#if visible.length}
						<EmailTable
							emails={visible}
							selectedId={selected?.id ?? null}
							onselect={(id) => (chosenId = id)}
						/>
					{:else}
						<div
							class="rounded-lg border border-dashed border-line-strong bg-surface px-6 py-10 text-center"
						>
							<p class="text-lg font-bold">
								{filters.query || filters.urgentOnly || filters.angry || filters.unsure
									? 'No emails match these filters.'
									: EMPTY[view]}
							</p>
						</div>
					{/if}

					<p class="text-sm text-muted">
						Also: {counts.inbox} in the inbox, {counts['in-progress']} in progress,
						{counts.closed} closed quietly.
						{#if view !== 'all'}
							<button
								type="button"
								class="cursor-pointer font-bold text-ink underline underline-offset-2"
								onclick={() => (view = 'all')}>Show all {counts.all}</button
							>
						{/if}
					</p>
				</main>

				{#if selected}
					<div class="lg:flex lg:w-panel lg:flex-none">
						<EmailPanel email={selected} {busy} onact={act} />
					</div>
				{/if}
			</div>
		{:else if loaded}
			<main class="flex flex-1 items-center justify-center p-6">
				<div
					class="flex max-w-md flex-col items-start gap-4 rounded-lg border border-line bg-surface p-6"
				>
					<h2 class="text-2xl font-extrabold">Start with a demo business</h2>
					<p class="text-body">
						Herald needs a workspace to sort mail into. The demo is Tripfold, an online luggage
						shop, with its topics and rules already set up.
					</p>
					<Button variant="primary" onclick={createDemo}>Create the Tripfold workspace</Button>
				</div>
			</main>
		{/if}
	</div>
</div>

<SendTestEmail bind:this={sender} onsend={send} />
<Toast message={toast} ondismiss={() => (toast = null)} />
