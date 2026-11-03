<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { untrack } from 'svelte';
	import {
		api,
		type Email,
		type Mailbox,
		type Workspace,
		type WorkspaceConfig
	} from '#lib/api/client.js';
	import { WorkspaceEvents } from '#lib/events.svelte.js';
	import BusinessMenu from '#lib/inbox/BusinessMenu.svelte';
	import EmailPanel from '#lib/inbox/EmailPanel.svelte';
	import EmailTable from '#lib/inbox/EmailTable.svelte';
	import QuestionDialog from '#lib/inbox/QuestionDialog.svelte';
	import QuestionStrip from '#lib/inbox/QuestionStrip.svelte';
	import ReplyBox from '#lib/inbox/ReplyBox.svelte';
	import { ReplyDesk, locked } from '#lib/inbox/replies.svelte.js';
	import { replyMailbox, replyState } from '#lib/inbox/reply.js';
	import ConnectGmail from '#lib/mailbox/ConnectGmail.svelte';
	import MailboxMenu from '#lib/mailbox/MailboxMenu.svelte';
	import { liveMailboxes, needsMailbox, readReturn, type Notice } from '#lib/mailbox/mailbox.js';
	import Rail from '#lib/shell/Rail.svelte';
	import {
		ACTIONS,
		EMPTY,
		VIEWS,
		actionsFor,
		countByView,
		questionActionsFor,
		questionsFor,
		senderName,
		visibleEmails,
		type Action,
		type Filters
	} from '#lib/inbox/inbox.js';
	import { inboxParams, viewFrom, withoutCallback } from '#lib/inbox/url.js';
	import { Button, FilterChip, STATUS, Tabs, Toast, type TabItem } from '#lib/ui/index.js';
	import { useSearchParams } from 'runed/kit';

	// Business, view, filters and the open email live on the URL. Replace, not push: picking
	// emails with j/k must not fill the back button. The debounce batches typing in search into
	// one URL change; reads still update at once. noScroll keeps runed from jumping to the top.
	const params = useSearchParams(inboxParams, {
		pushHistory: false,
		debounce: 250,
		noScroll: true
	});

	let workspaces = $state.raw<Workspace[]>([]);
	let emails = $state.raw<Email[]>([]);
	let loaded = $state(false);
	let error = $state<string | null>(null);
	let toast = $state<string | null>(null);
	let busy = $state(false);

	let mailboxes = $state.raw<Mailbox[]>([]);
	// The workspace `mailboxes` belongs to. Until it matches, we don't know yet whether the
	// business is open, so neither the inbox nor the connect screen shows.
	let mailboxesFor = $state<string | null>(null);
	let providers = $state.raw<string[]>([]);
	let notice = $state<Notice | null>(null);
	let connecting = $state(false);

	const view = $derived(viewFrom(params.view));
	// Search keeps its own copy. runed copies the URL back over its values whenever the URL
	// changes, so a key typed while an earlier URL update lands would be lost from the box.
	let query = $state(params.q);
	const filters = $derived<Filters>({
		query,
		urgentOnly: params.urgent
	});
	// The email the owner opened in full. Keyed by id, so picking another email folds it again.
	let fullId = $state<string | null>(null);
	// The question the owner opened, and the email Herald is re-reading after they answered it.
	let askingId = $state<string | null>(null);
	let rereading = $state<{ id: string; sender: string } | null>(null);

	let search = $state<HTMLInputElement>();

	const live = new WorkspaceEvents();
	// Only a saved setup takes email; drafts wait in the business menu.
	const ready = $derived(workspaces.filter((w) => w.setup_done));
	const firstDraft = $derived(workspaces.find((w) => !w.setup_done));
	// An unknown or stale id on the URL falls back to the first business.
	const workspace = $derived(ready.find((w) => w.id === params.workspace) ?? ready[0]);
	const workspaceId = $derived(workspace?.id ?? null);
	const checked = $derived(!!workspace && mailboxesFor === workspace.id);
	// A business with no mailbox stays closed: the connect screen is all it shows.
	const gated = $derived(!!workspace && checked && needsMailbox(workspace, mailboxes));
	const open = $derived(!!workspace && checked && !gated);
	const mailbox = $derived(liveMailboxes(mailboxes)[0]);
	const counts = $derived(countByView(emails));
	const visible = $derived(visibleEmails(emails, view, filters));
	const questions = $derived(questionsFor(emails));
	// Closes by itself once the email stops asking, say after On it from another tab.
	const asking = $derived(questions.find((e) => e.id === askingId) ?? null);
	// The email the owner just replied to stays open, even once "Send and mark done" drops it
	// from the view, so its "Your replies" shows. J/K, a row click or a tab lets it go.
	let pinnedId = $state<string | null>(null);
	const pinned = $derived(emails.find((e) => e.id === pinnedId) ?? null);
	// Keep the owner's choice while it is in view; otherwise open the top email.
	const selected = $derived(
		pinned ?? visible.find((e) => e.id === params.email) ?? visible[0] ?? null
	);

	const replies = new ReplyDesk({
		onsent: (message, emailId, shown) => {
			toast = message;
			// Only if the panel still shows it: the owner may have moved on while the POST
			// was out, and pinning would pull the panel back to the answered email.
			if (shown) pinnedId = emailId;
			if (workspaceId) refresh(workspaceId);
		},
		onmailbox: () => workspaceId && refreshMailboxes(workspaceId),
		onerror: fail
	});
	// The email being answered, found in all emails rather than the view: a reply marked done
	// elsewhere leaves the view, and the composer must not slide over to the next customer.
	const composing = $derived(emails.find((e) => e.id === replies.composingId) ?? null);
	const draft = $derived(composing ? replies.drafts[composing.id] : undefined);
	// The email in the panel and the one O/N/I/D/E act on: while composing, the one answered.
	const current = $derived(composing ?? selected);
	const currentId = $derived(current?.id ?? null);
	const canReply = $derived(current ? replyState(current, mailboxes) : 'no_mailbox');
	const tabs = $derived<TabItem[]>(
		VIEWS.map((v) => ({ id: v.id, label: v.label, count: counts[v.id], countTone: v.countTone }))
	);

	api
		.listWorkspaces()
		.then((list) => {
			workspaces = list;
			// Google's callback names the business the connect started from on the URL; setup
			// sends the owner here with the saved workspace in the page state.
			const back = readReturn(page.url.searchParams);
			notice = back.notice;
			const rest = withoutCallback(page.url.search);
			// The path is resolve('/'); the rule can't see through the added query.
			// eslint-disable-next-line svelte/no-navigation-without-resolve
			if (rest !== null) goto(`${resolve('/')}${rest}`, { replace: true, reset: false });
			// The callback already put its business on the URL as `workspace`.
			if (!back.workspace && page.state.workspace) params.workspace = page.state.workspace;
			loaded = true;
		})
		.catch(fail);

	// Not fatal: with no providers the connect screen says Gmail isn't set up.
	api
		.listProviders()
		.then((list) => (providers = list))
		.catch(() => (providers = []));

	$effect(() => {
		if (!workspaceId) return;
		const id = workspaceId;
		refresh(id);
		refreshMailboxes(id);
		// Drafts saved before a reload, or before the trip to Google on Reconnect. Untracked:
		// restore reads the drafts, and this effect must not rerun when one changes.
		untrack(() => replies.restore(id));
		live.connect(id);
		const stop = live.onEvent((event) => {
			if (event.type === 'mailbox.status') return refreshMailboxes(id);
			// Another tab's send, or this one's settling: the panel's list catches up.
			if (event.type === 'reply.status') {
				if (current && event.data.email_id === current.id) replies.load(current);
				return;
			}
			const done = event.type === 'email.noted' ? rereading : null;
			if (done && event.data.email_id === done.id) {
				toast = rereadOutcome(done.sender, event.data);
				rereading = null;
			}
			refresh(id);
		});
		return () => {
			stop();
			live.close();
		};
	});

	// The panel's replies load when another email opens, not on every refresh of the list.
	$effect(() => {
		if (!currentId) return;
		const email = untrack(() => current);
		if (email) replies.load(email);
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

	async function refreshMailboxes(id: string) {
		try {
			mailboxes = await api.listMailboxes(id);
			mailboxesFor = id;
		} catch (e) {
			fail(e);
		}
	}

	async function connectGmail() {
		if (!workspaceId || connecting) return;
		connecting = true;
		try {
			const { authorization_url } = await api.startConnect(workspaceId, 'gmail');
			// A full page redirect: Google sends the browser back to / with the outcome on the URL.
			window.location.assign(authorization_url);
		} catch (e) {
			connecting = false;
			fail(e);
		}
	}

	async function mailboxAct(
		run: (workspaceId: string, mailboxId: string) => Promise<Mailbox>,
		done: string
	) {
		if (!mailbox || busy) return;
		busy = true;
		try {
			const updated = await run(mailbox.workspace_id, mailbox.id);
			mailboxes = mailboxes.map((m) => (m.id === updated.id ? updated : m));
			toast = done;
		} catch (e) {
			fail(e);
		} finally {
			busy = false;
		}
	}

	function disconnect() {
		if (!mailbox) return;
		const sure = confirm(
			`Disconnect ${mailbox.email_address}? Herald stops reading it. Emails already here stay.`
		);
		if (sure) mailboxAct(api.disconnectMailbox, `Disconnected ${mailbox.email_address}.`);
	}

	async function createDemo() {
		try {
			const created = await api.createDemoWorkspace();
			workspaces = [...workspaces, created];
			chooseWorkspace(created.id);
		} catch (e) {
			fail(e);
		}
	}

	async function act(
		action: Action,
		email: Email | null = current,
		allowed: (status: Email['status']) => Action[] = actionsFor
	) {
		if (!email || busy || !allowed(email.status).includes(action)) return;
		busy = true;
		try {
			const updated = await api.act(email.workspace_id, email.id, action);
			emails = emails.map((e) => (e.id === updated.id ? updated : e));
			toast = ACTIONS[action].done;
		} catch (e) {
			fail(e);
		} finally {
			busy = false;
		}
	}

	// Another business's email id means nothing here, so switching drops it.
	function chooseWorkspace(id: string | null) {
		replies.close();
		pinnedId = null;
		params.update({ workspace: id ?? '', email: '' });
	}

	// A tab means the owner wants the list back. The draft stays for when they return.
	function chooseView(id: string) {
		replies.close();
		pinnedId = null;
		params.view = id;
	}

	// Save the owner's fact and rule changes (none when they only asked for a rerun), then have
	// Herald read the email again. The answer arrives later as email.noted; until then the
	// question stays up with its old notes.
	async function keep(email: Email, config: WorkspaceConfig | null) {
		if (!workspace || busy) return;
		busy = true;
		const what = config ? 'Changes saved. ' : '';
		try {
			if (config) {
				const saved = await api.saveConfig(workspace.id, workspace.name, config);
				workspaces = workspaces.map((w) => (w.id === saved.id ? saved : w));
			}
			askingId = null;
			// Set before the request: in lite mode the re-read can finish before it returns.
			rereading = { id: email.id, sender: senderName(email.sender) };
			toast = `${what}Herald is re-reading ${rereading.sender}’s email.`;
			await api.reread(email.workspace_id, email.id);
		} catch (e) {
			const refused = rereading && e instanceof Error && e.message.startsWith('409');
			rereading = null;
			// The changes are saved; only the re-read was refused, because the owner already
			// moved this email by hand. Say so instead of showing an error.
			if (refused)
				toast = `${what}You moved this email yourself, so Herald leaves it there. Mark it Done or On it to clear the question.`;
			else fail(e);
		} finally {
			busy = false;
		}
	}

	function rereadOutcome(sender: string, data: Record<string, unknown>): string {
		const status = STATUS[data.status as Email['status']]?.label ?? 'sorted';
		const notes = data.notes as Email['notes'];
		return notes?.sure === false
			? `Herald re-read ${sender}’s email and is still unsure. It’s in ${status}.`
			: `Herald re-read ${sender}’s email: ${status}.`;
	}

	function move(step: number) {
		// The list is hidden while composing; moving would change the panel under the draft.
		if (composing || !visible.length) return;
		// Step from the open email, pinned or not. One that left the view starts from the top.
		const from = selected;
		pinnedId = null;
		const index = from ? visible.indexOf(from) : -1;
		params.email = visible[Math.min(visible.length - 1, Math.max(0, index + step))].id;
	}

	function toggleFull() {
		if (current) fullId = fullId === current.id ? null : current.id;
	}

	// Only from the open email, never from a table row: the panel's notes stay beside the draft.
	function openReply() {
		if (!current || canReply !== 'ok') return;
		if (replies.composingId === current.id) document.getElementById('reply-body')?.focus();
		else replies.open(current);
	}

	// Owner shortcuts, from docs/design-system.md. Never while typing or in a dialog.
	function onkeydown(event: KeyboardEvent) {
		const target = event.target as HTMLElement;
		if (!open || event.metaKey || event.ctrlKey || event.altKey) return;
		if (target.closest('input, textarea, select, dialog[open]')) return;
		const keys: Record<string, () => void> = {
			j: () => move(1),
			ArrowDown: () => move(1),
			k: () => move(-1),
			ArrowUp: () => move(-1),
			o: () => act('on-it'),
			n: () => act('not-urgent'),
			i: () => act('to-inbox'),
			d: () => act('done'),
			e: toggleFull,
			r: openReply,
			'/': () => !composing && search?.focus()
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

	<!-- Wide screens: fit the viewport so the list and the email panel scroll on their own.
		Otherwise a long email scrolls the list and header away with it. -->
	<div class={['flex min-w-0 flex-1 flex-col', open && 'lg:h-screen']}>
		<header
			class="flex flex-wrap items-end justify-between gap-3 border-b border-line px-4 pt-2.5 lg:border-b-0"
		>
			{#if open}
				<Tabs items={tabs} bind:selected={() => view, chooseView} label="Inbox views" />
			{:else}
				<p class="pb-2 text-2xl font-extrabold">{workspace?.name ?? 'Herald'}</p>
			{/if}
			<div class="flex flex-wrap items-center gap-3 pb-1.5">
				{#if open}
					<span class="inline-flex items-center gap-1.5 text-sm text-neutral-fg">
						<span class={['size-2 rounded-full', live.connected ? 'bg-live' : 'bg-line-strong']}
						></span>
						{live.connected ? 'Live' : 'Connecting'}
					</span>
				{/if}
				{#if open && mailbox}
					<MailboxMenu
						{mailbox}
						{busy}
						onsync={() =>
							mailboxAct((w, m) => api.mailboxAction(w, m, 'sync'), 'Checking for new mail.')}
						onpause={() =>
							mailboxAct(
								(w, m) => api.mailboxAction(w, m, 'pause'),
								'Paused. Mail waits in Gmail.'
							)}
						onresume={() =>
							mailboxAct(
								(w, m) => api.mailboxAction(w, m, 'resume'),
								'Resumed. Herald is catching up.'
							)}
						ondisconnect={disconnect}
						onreconnect={connectGmail}
					/>
				{/if}
				{#if workspaces.length}
					<BusinessMenu {workspaces} bind:selected={() => workspaceId, chooseWorkspace} />
				{/if}
			</div>
		</header>

		{#if error}
			<div
				role="alert"
				class="mx-4 mt-3 flex items-start justify-between gap-3 rounded-lg bg-danger-bg px-4 py-2 text-sm text-danger-fg"
			>
				<!-- With HERALD_DEBUG the message is a full traceback: keep its lines, cap its height. -->
				<p class="max-h-64 min-w-0 overflow-auto break-words">
					Something went wrong: <span class="whitespace-pre-wrap">{error}</span>
				</p>
				<Button variant="quiet" size="sm" onclick={() => (error = null)}>Dismiss</Button>
			</div>
		{/if}

		{#if notice}
			<div
				role={notice.tone === 'danger' ? 'alert' : 'status'}
				class={[
					'mx-4 mt-3 flex flex-wrap items-center gap-3 rounded-lg px-4 py-2.5 text-sm',
					notice.tone === 'danger' ? 'bg-danger-bg text-danger-fg' : 'bg-success-bg text-success-fg'
				]}
			>
				<p class="flex-1"><b>{notice.title}</b> {notice.text}</p>
				{#if notice.retry && workspace}
					<Button size="sm" disabled={connecting} onclick={connectGmail}>Try again</Button>
				{/if}
				<Button variant="quiet" size="sm" onclick={() => (notice = null)}>Dismiss</Button>
			</div>
		{/if}

		{#if open && mailbox?.status === 'needs_reauth'}
			<div
				role="alert"
				class="mx-4 mt-3 flex flex-wrap items-center gap-3 rounded-lg bg-danger-bg px-4 py-2.5 text-sm text-danger-fg"
			>
				<p class="flex-1">
					<b>Herald has stopped reading {mailbox.email_address}.</b> Google access ended, so new mail
					can’t alert you. Nothing is lost: Herald catches up when you reconnect.
				</p>
				<Button variant="primary" size="sm" disabled={connecting} onclick={connectGmail}
					>Reconnect Gmail</Button
				>
			</div>
		{/if}

		{#if open}
			<div class="flex flex-1 flex-col lg:min-h-0 lg:flex-row">
				<main
					class="flex min-w-0 flex-1 flex-col gap-3 p-4 lg:overflow-y-auto lg:border-t lg:border-line"
				>
					{#if composing && draft}
						<ReplyBox
							email={composing}
							from={replyMailbox(composing, mailboxes)?.email_address}
							state={canReply}
							bind:body={
								() => draft?.body ?? '', (body) => composing && replies.setBody(composing, body)
							}
							sending={draft.sending}
							waiting={!!draft.waiting}
							locked={locked(draft)}
							last={draft.last}
							problem={draft.problem}
							{connecting}
							onsend={(markDone) => composing && replies.send(composing, markDone)}
							onclose={() => replies.close()}
							ondiscard={() => composing && replies.discard(composing)}
							onreconnect={connectGmail}
						/>
					{:else}
						{#if questions.length}
							<QuestionStrip {questions} onanswer={(id) => (askingId = id)} />
						{/if}

						<div class="flex flex-wrap items-center gap-2">
							<label class="sr-only" for="search">Search mail</label>
							<input
								id="search"
								bind:this={search}
								bind:value={query}
								oninput={() => (params.q = query)}
								type="search"
								placeholder="Search mail  /"
								class="h-control-md w-56 rounded-sm border border-control bg-surface px-2.5 text-sm"
							/>
							<FilterChip bind:pressed={params.urgent}>Urgent</FilterChip>
						</div>

						{#if visible.length}
							<EmailTable
								emails={visible}
								selectedId={selected?.id ?? null}
								onselect={(id) => {
									pinnedId = null;
									params.email = id;
								}}
							/>
						{:else}
							<div
								class="rounded-lg border border-dashed border-line-strong bg-surface px-6 py-10 text-center"
							>
								<p class="text-lg font-bold">
									{filters.query || filters.urgentOnly
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
									onclick={() => chooseView('all')}>Show all {counts.all}</button
								>
							{/if}
						</p>
					{/if}
				</main>

				{#if current}
					<!-- At phone width the composer takes the screen, as the list does there. -->
					<div
						class={[
							'px-4 pb-4 lg:flex lg:w-panel lg:flex-none lg:border-t lg:border-line lg:py-4 lg:pr-4 lg:pl-0',
							composing && 'max-lg:hidden'
						]}
					>
						<EmailPanel
							email={current}
							{busy}
							full={fullId === current.id}
							ontogglefull={toggleFull}
							onact={act}
							replyState={canReply}
							replies={replies.list}
							{connecting}
							onreply={openReply}
							onreconnect={connectGmail}
						/>
					</div>
				{/if}
			</div>
		{:else if gated && workspace}
			<ConnectGmail
				business={workspace.name}
				available={providers.includes('gmail')}
				busy={connecting}
				onconnect={connectGmail}
			/>
		{:else if loaded && !workspace}
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

{#if asking && workspace}
	{#key asking.id}
		{@const question = asking}
		<QuestionDialog
			email={asking}
			config={workspace.config}
			{busy}
			ontry={(config) => api.tryConfig(workspace.id, question.id, config)}
			onkeep={(config) => asking && keep(asking, config)}
			onact={(action) => act(action, asking, questionActionsFor)}
			onclose={() => (askingId = null)}
		/>
	{/key}
{/if}

<Toast message={toast} ondismiss={() => (toast = null)} />
