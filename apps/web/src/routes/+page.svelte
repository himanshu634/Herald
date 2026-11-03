<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { api, type Email, type EmailIn, type Workspace } from '#lib/api/client.js';
	import { WorkspaceEvents } from '#lib/events.svelte.js';
	import BusinessMenu from '#lib/inbox/BusinessMenu.svelte';
	import EmailPanel from '#lib/inbox/EmailPanel.svelte';
	import EmailTable from '#lib/inbox/EmailTable.svelte';
	import SendTestEmail from '#lib/inbox/SendTestEmail.svelte';
	import Rail from '#lib/shell/Rail.svelte';
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
	import { Button, FilterChip, Tabs, Toast, type TabItem } from '#lib/ui/index.js';

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
	// Only a saved setup takes email; drafts wait in the business menu.
	const ready = $derived(workspaces.filter((w) => w.setup_done));
	const firstDraft = $derived(workspaces.find((w) => !w.setup_done));
	const workspace = $derived(ready.find((w) => w.id === workspaceId));
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
			// Setup sends the owner here with the saved workspace in the page state.
			const asked = page.state.workspace;
			const usable = list.filter((w) => w.setup_done);
			workspaceId = (usable.find((w) => w.id === asked) ?? usable[0])?.id ?? null;
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
	<Rail />

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
				{#if workspace}
					<span class="inline-flex items-center gap-1.5 text-sm text-neutral-fg">
						<span class={['size-2 rounded-full', live.connected ? 'bg-live' : 'bg-line-strong']}
						></span>
						{live.connected ? 'Live' : 'Connecting'}
					</span>
				{/if}
				{#if workspaces.length}
					<BusinessMenu {workspaces} bind:selected={workspaceId} />
				{/if}
				{#if workspace}
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
				<div class="flex w-full max-w-190 flex-col gap-5">
					<div>
						<h2 class="text-2xl font-extrabold tracking-title">Who does Herald read mail for?</h2>
						<p class="mt-1.5 text-muted">
							Each business gets its own topics and rules. You can add more businesses later.
						</p>
					</div>
					<div class="flex flex-wrap gap-4">
						<div
							class="flex min-w-64 flex-1 flex-col gap-3 rounded-lg border-[1.5px] border-ink bg-surface p-5"
						>
							{#if firstDraft}
								<h3 class="text-lg font-extrabold">Finish setting up {firstDraft.name}</h3>
								<p class="text-sm text-body">
									Herald has drafted its topics and rules. Check them and save to start sorting
									mail.
								</p>
								<Button
									variant="primary"
									class="mt-auto self-start"
									onclick={() =>
										goto(resolve('/setup/[[workspace]]', { workspace: firstDraft.id }))}
									>Finish setup</Button
								>
							{:else}
								<h3 class="text-lg font-extrabold">Set up your business</h3>
								<p class="text-sm text-body">
									Tell Herald what you sell and what a bad day looks like. It drafts your topics and
									rules, and you check them. About two minutes.
								</p>
								<Button
									variant="primary"
									class="mt-auto self-start"
									onclick={() => goto(resolve('/setup/[[workspace]]', {}))}
									>Set up your business</Button
								>
							{/if}
						</div>
						<div
							class="flex min-w-64 flex-1 flex-col gap-3 rounded-lg border border-line bg-surface p-5"
						>
							<h3 class="text-lg font-extrabold">Try the demo</h3>
							<p class="text-sm text-body">
								Tripfold, an online luggage shop, with its topics and rules already set up.
							</p>
							<Button class="mt-auto self-start" onclick={createDemo}>Open the Tripfold demo</Button
							>
						</div>
					</div>
				</div>
			</main>
		{/if}
	</div>
</div>

<SendTestEmail bind:this={sender} onsend={send} />
<Toast message={toast} ondismiss={() => (toast = null)} />
