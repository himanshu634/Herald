<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { api, type WorkspaceConfig } from '#lib/api/client.js';
	import SetupEditor from '#lib/setup/SetupEditor.svelte';
	import Rail from '#lib/shell/Rail.svelte';
	import { MAX_DESCRIPTION, isEdited, problems } from '#lib/setup/setup.js';
	import { Button, Icon } from '#lib/ui/index.js';

	// Onboarding, direction P on the design canvas: step 1 is the name and description, step 2
	// is Herald's draft to check. The workspace exists from step 1 on, as a draft that takes no
	// email, so /setup/<id> resumes at step 2.
	const resumeId = page.params.workspace ?? null;
	let workspaceId = $state<string | null>(resumeId);
	let step = $state<'about' | 'draft'>(resumeId ? 'draft' : 'about');
	let name = $state('');
	let description = $state('');
	let config = $state<WorkspaceConfig | null>(null);
	// What Herald last drafted, to tell whether the owner has changed it.
	let draft = $state.raw<WorkspaceConfig | null>(null);
	let drafted = $state(true);
	let busy = $state(false);
	let error = $state<string | null>(null);
	let confirmRedraft = $state(false);
	let showProblems = $state(false);

	const found = $derived(config ? problems(config) : []);

	if (resumeId) {
		api
			.getWorkspace(resumeId)
			.then((w) => {
				name = w.name;
				description = w.config.business_profile;
				load(w.config, true);
			})
			.catch(() => {
				// A stale link: start over rather than show a broken page.
				workspaceId = null;
				step = 'about';
			});
	}

	function load(next: WorkspaceConfig, wasDrafted: boolean) {
		config = structuredClone(next);
		draft = next;
		drafted = wasDrafted;
		confirmRedraft = false;
		showProblems = false;
		step = 'draft';
	}

	async function run(job: () => Promise<void>) {
		busy = true;
		error = null;
		try {
			await job();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			busy = false;
		}
	}

	function submitAbout(event: SubmitEvent) {
		event.preventDefault();
		if (busy || !name.trim() || !description.trim()) return;
		run(async () => {
			if (workspaceId) {
				// Back from step 2 with a new description: draft again, the workspace stays.
				const out = await api.suggestSetup(workspaceId, description.trim());
				load(out.config, out.drafted);
				return;
			}
			const out = await api.startSetup(name.trim(), description.trim());
			workspaceId = out.workspace.id;
			// Put the id in the address, so a reload resumes at step 2.
			await goto(resolve('/setup/[[workspace]]', { workspace: out.workspace.id }), {
				replaceState: true
			});
			load(out.workspace.config, out.drafted);
		});
	}

	function redraft() {
		if (!workspaceId || !config) return;
		if (draft && isEdited(draft, config) && !confirmRedraft) {
			confirmRedraft = true;
			return;
		}
		const id = workspaceId;
		run(async () => {
			const out = await api.suggestSetup(id, description.trim());
			load(out.config, out.drafted);
		});
	}

	function save() {
		if (!workspaceId || !config || busy) return;
		if (found.length) {
			showProblems = true;
			return;
		}
		const id = workspaceId;
		const saved = config;
		run(async () => {
			await api.saveConfig(id, name.trim(), saved);
			await goto(resolve('/'), { state: { workspace: id } });
		});
	}

	function onkeydown(event: KeyboardEvent) {
		if (step === 'draft' && event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
			event.preventDefault();
			save();
		}
	}
</script>

<svelte:window {onkeydown} />
<svelte:head><title>Set up a business · Herald</title></svelte:head>

{#snippet steps(n: 1 | 2)}
	<div class="flex items-center gap-1.5 text-sm text-muted">
		<span class="h-1 w-11 rounded-full bg-ink"></span>
		<span class={['h-1 w-11 rounded-full', n === 2 ? 'bg-ink' : 'bg-line']}></span>
		<span class="ml-1">Step {n} of 2</span>
	</div>
{/snippet}

<div class="flex min-h-screen">
	<Rail />

	<div class="flex min-w-0 flex-1 flex-col">
		<header class="flex h-14 items-center justify-between gap-3 px-5">
			<p class="text-sm text-muted">
				New business{#if step === 'draft' && name}&nbsp;/ <b class="text-ink">{name}</b>{/if}
			</p>
			{#if workspaceId}
				<span class="rounded-xs bg-warning-bg px-1.5 text-xs font-bold text-warning-fg">Draft</span>
			{/if}
		</header>

		{#if error}
			<div
				role="alert"
				class="mx-auto mb-3 flex w-full max-w-190 items-center justify-between gap-3 rounded-lg bg-danger-bg px-4 py-2 text-sm text-danger-fg"
			>
				<p>Herald couldn't do that: {error}</p>
				<Button variant="quiet" size="sm" onclick={() => (error = null)}>Dismiss</Button>
			</div>
		{/if}

		{#if step === 'about'}
			<main class="flex justify-center px-5 pt-2 pb-10">
				<form
					class="flex w-full max-w-160 flex-col gap-5 rounded-lg border border-line bg-surface p-7"
					onsubmit={submitAbout}
				>
					{@render steps(1)}
					<div>
						<h1 class="text-2xl font-extrabold tracking-title">Tell Herald about your business</h1>
						<p class="mt-1.5 text-muted">Herald reads every customer email with this in mind.</p>
					</div>
					<div class="flex flex-col gap-1.5">
						<label class="text-sm font-bold" for="name">Business name</label>
						<input
							id="name"
							bind:value={name}
							required
							maxlength={100}
							autocomplete="organization"
							class="h-10 rounded-sm border border-control bg-surface px-3 text-md"
						/>
					</div>
					<div class="flex flex-col gap-1.5">
						<label class="text-sm font-bold" for="description">What you do</label>
						<textarea
							id="description"
							bind:value={description}
							required
							rows="6"
							maxlength={MAX_DESCRIPTION}
							aria-describedby="description-hint"
							placeholder="We bake custom cakes to order and deliver them on the day. A bad day is a cake that arrives late for a wedding."
							class="resize-y rounded-sm border border-control bg-surface px-3 py-2 text-md leading-relaxed"
						></textarea>
						<div id="description-hint" class="flex justify-between gap-3 text-sm text-muted">
							<span>What you sell, who your customers are, and what a bad day looks like.</span>
							<span class="tabular-nums">{description.length} / {MAX_DESCRIPTION}</span>
						</div>
					</div>
					<hr class="border-t border-dashed border-line-dashed" />
					<div class="flex items-center justify-between gap-3">
						{#if workspaceId}
							<Button variant="quiet" onclick={() => (step = 'draft')}>Back to the draft</Button>
						{:else}
							<a
								href={resolve('/')}
								class="text-sm font-bold text-neutral-fg underline-offset-2 hover:underline"
								>Cancel</a
							>
						{/if}
						<Button
							variant="primary"
							type="submit"
							disabled={busy || !name.trim() || !description.trim()}
						>
							{busy ? 'Herald is reading…' : workspaceId ? 'Draft again' : 'Draft my setup'}
						</Button>
					</div>
				</form>
			</main>
		{:else if config}
			<main class="flex justify-center px-5 pt-2">
				<div class="flex w-full max-w-190 flex-col gap-4">
					{@render steps(2)}
					<div>
						<h1 class="text-2xl font-extrabold tracking-title">Check what Herald understood</h1>
						<p class="mt-1.5 text-muted">
							Edit anything. Nothing is live until you save.
							<button
								type="button"
								class="cursor-pointer font-bold text-ink underline underline-offset-2"
								onclick={() => (step = 'about')}>Change the description</button
							>
						</p>
					</div>

					{#if !drafted}
						<div
							role="status"
							class="flex items-start gap-2.5 rounded-md bg-warning-bg px-4 py-3 text-sm text-warning-fg"
						>
							<Icon name="alert" size={18} />
							<p>
								<b>Herald couldn't draft this just now.</b> Start from these three topics and add your
								own rules, or press Redraft in a minute.
							</p>
						</div>
					{/if}

					<SetupEditor bind:config />

					<div
						class="sticky bottom-0 mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line-strong bg-surface px-4 py-3"
					>
						<div class="flex flex-wrap items-center gap-3">
							{#if confirmRedraft}
								<p class="text-sm font-semibold">Replace your edits with a new draft?</p>
								<Button size="sm" onclick={redraft} disabled={busy}>Replace</Button>
								<Button variant="quiet" size="sm" onclick={() => (confirmRedraft = false)}
									>Keep editing</Button
								>
							{:else}
								<Button onclick={redraft} disabled={busy}
									><Icon name="redo" size={16} />Redraft</Button
								>
								<span class="text-sm text-muted"
									>Reads your description again and replaces this draft.</span
								>
							{/if}
						</div>
						<Button variant="primary" kbd="⌘↵" onclick={save} disabled={busy}>
							{busy ? 'Saving…' : 'Save and open inbox'}
						</Button>
						{#if showProblems && found.length}
							<ul role="alert" class="w-full text-sm font-semibold text-danger-fg">
								{#each found as problem (problem)}<li>{problem}</li>{/each}
							</ul>
						{/if}
					</div>
				</div>
			</main>
		{:else}
			<p class="px-5 text-muted">Loading the draft…</p>
		{/if}
	</div>
</div>
