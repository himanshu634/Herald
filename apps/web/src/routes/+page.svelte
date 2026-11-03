<script lang="ts">
	import { api, type Email, type Workspace } from '#lib/api/client.js';
	import { WorkspaceEvents } from '#lib/events.svelte.js';

	let workspaces = $state.raw<Workspace[]>([]);
	let workspaceId = $state<string | null>(null);
	let emails = $state.raw<Email[]>([]);
	let error = $state<string | null>(null);
	let draft = $state({ sender: 'riya@customer.in', subject: '', body: '' });

	const live = new WorkspaceEvents();
	const workspace = $derived(workspaces.find((w) => w.id === workspaceId));

	api
		.listWorkspaces()
		.then((list) => {
			workspaces = list;
			workspaceId = list[0]?.id ?? null;
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

	function fail(e: unknown) {
		error = e instanceof Error ? e.message : String(e);
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

	async function send(event: SubmitEvent) {
		event.preventDefault();
		if (!workspaceId) return;
		try {
			await api.sendTestEmail(workspaceId, draft);
			draft = { ...draft, subject: '', body: '' };
		} catch (e) {
			fail(e);
		}
	}

	async function act(email: Email, action: 'on-it' | 'not-urgent' | 'done') {
		try {
			await api.act(email.workspace_id, email.id, action);
		} catch (e) {
			fail(e);
		}
	}
</script>

<main>
	<header>
		<h1>Herald</h1>
		{#if workspaces.length}
			<select bind:value={workspaceId} aria-label="Workspace">
				{#each workspaces as w (w.id)}
					<option value={w.id}>{w.name}</option>
				{/each}
			</select>
		{/if}
		<button onclick={createDemo}>New demo workspace</button>
		<span class={['dot', live.connected && 'on']} title={live.connected ? 'Live' : 'Offline'}
		></span>
	</header>

	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}

	{#if workspace}
		<section>
			<h2>Send a test email to {workspace.name}</h2>
			<form onsubmit={send}>
				<input bind:value={draft.sender} placeholder="From" required />
				<input bind:value={draft.subject} placeholder="Subject" required />
				<textarea bind:value={draft.body} placeholder="Body" rows="4" required></textarea>
				<button type="submit">Send</button>
			</form>
		</section>

		<section>
			<h2>Inbox</h2>
			{#if emails.length === 0}
				<p class="muted">No emails yet.</p>
			{/if}
			<ul>
				{#each emails as email (email.id)}
					<li>
						<span class={['status', email.status]}>{email.status.replaceAll('_', ' ')}</span>
						<strong>{email.subject}</strong>
						<span class="muted">{email.sender}</span>
						{#if email.decision}
							<span class="muted">— {email.decision.reason}</span>
						{/if}
						{#if email.status === 'alerted'}
							<button onclick={() => act(email, 'on-it')}>On it</button>
							<button onclick={() => act(email, 'not-urgent')}>Not urgent</button>
						{:else if email.status === 'in_progress'}
							<button onclick={() => act(email, 'done')}>Done</button>
						{/if}
					</li>
				{/each}
			</ul>
		</section>

		<section>
			<h2>Live events</h2>
			<ol class="log">
				{#each live.events as event (event.id)}
					<li><code>{event.id}</code> {event.type}</li>
				{/each}
			</ol>
		</section>
	{:else}
		<p class="muted">Create a demo workspace to start.</p>
	{/if}
</main>

<style>
	main {
		max-width: 52rem;
		margin: 0 auto;
		padding: 1.5rem 1rem;
		font-family: system-ui, sans-serif;
	}
	header {
		display: flex;
		gap: 0.75rem;
		align-items: center;
	}
	h1 {
		margin: 0 auto 0 0;
	}
	form {
		display: grid;
		gap: 0.5rem;
	}
	ul {
		list-style: none;
		padding: 0;
	}
	li {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: center;
		padding: 0.5rem 0;
		border-bottom: 1px solid #ddd;
	}
	.muted {
		color: #666;
	}
	.error {
		color: #b00020;
	}
	.status {
		font-size: 0.75rem;
		text-transform: uppercase;
		padding: 0.1rem 0.4rem;
		border-radius: 0.25rem;
		background: #eee;
	}
	.status.alerted {
		background: #ffd6d6;
	}
	.status.needs_a_look {
		background: #fff1c2;
	}
	.dot {
		width: 0.6rem;
		height: 0.6rem;
		border-radius: 50%;
		background: #bbb;
	}
	.dot.on {
		background: #2e9d4f;
	}
	.log {
		font-size: 0.85rem;
	}
</style>
