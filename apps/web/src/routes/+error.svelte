<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import LostMail from '#lib/shell/LostMail.svelte';
	import { Button } from '#lib/ui/index.js';

	// Every route's error lands here, including unknown paths in the static SPA (404).
	const missing = $derived(page.status === 404);
	// SvelteKit's stock messages ("Not Found", "Internal Error") say less than the copy below.
	const detail = $derived.by(() => {
		const message = page.error?.message;
		return message && !['Not Found', 'Internal Error'].includes(message) ? message : null;
	});
</script>

<svelte:head>
	<title>{missing ? 'Page not found' : 'Something went wrong'} · Herald</title>
</svelte:head>

<main class="grid min-h-screen place-items-center bg-canvas px-6 py-12">
	<div class="flex w-full max-w-md flex-col items-center gap-6 text-center">
		<LostMail class="w-full max-w-sm" />

		<div class="flex flex-col gap-2">
			<p class="font-mono text-xs text-muted">
				{page.status} · {missing ? 'Page not found' : 'Something went wrong'}
			</p>
			<h1 class="text-2xl font-extrabold text-ink">
				{missing ? 'This one slipped out of the pile.' : 'Herald tripped over this one.'}
			</h1>
			<p class="text-md text-body">
				{#if missing}
					Herald looked through every row and couldn't find this page. The link may be old, or the
					page has moved.
				{:else}
					Something broke while loading this page. Try again, and if it keeps happening, head back
					to the inbox.
				{/if}
			</p>
			{#if detail}
				<p class="font-mono text-xs break-words text-muted">{detail}</p>
			{/if}
		</div>

		<div class="flex flex-wrap items-center justify-center gap-3">
			{#if !missing}
				<Button onclick={() => location.reload()}>Try again</Button>
			{/if}
			<Button variant="primary" onclick={() => goto(resolve('/'))}>Back to the inbox</Button>
		</div>
	</div>
</main>
