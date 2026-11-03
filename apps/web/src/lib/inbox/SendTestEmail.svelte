<script lang="ts">
	import type { EmailIn } from '#lib/api/client.js';
	import { Button } from '#lib/ui/index.js';

	let { onsend }: { onsend: (email: EmailIn) => Promise<void> } = $props();

	let dialog = $state<HTMLDialogElement>();
	let draft = $state({ sender: 'riya@customer.in', subject: '', body: '' });
	let sending = $state(false);

	export function open() {
		dialog?.showModal();
	}

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		sending = true;
		try {
			await onsend(draft);
			draft = { ...draft, subject: '', body: '' };
			dialog?.close();
		} finally {
			sending = false;
		}
	}

	const field =
		'h-control-md w-full rounded-sm border border-control bg-surface px-2.5 text-md text-ink';
</script>

<dialog
	bind:this={dialog}
	aria-labelledby="send-title"
	class="m-auto w-full max-w-lg rounded-xl border border-line bg-surface p-0 text-ink shadow-popover backdrop:bg-ink/40"
>
	<form class="flex flex-col gap-4 p-5" onsubmit={submit}>
		<div>
			<h2 id="send-title" class="text-xl font-extrabold">Send a test email</h2>
			<p class="text-sm text-muted">Herald reads it like a real customer email and sorts it.</p>
		</div>
		<label class="flex flex-col gap-1 text-sm font-semibold">
			From
			<input class={field} type="email" bind:value={draft.sender} required />
		</label>
		<label class="flex flex-col gap-1 text-sm font-semibold">
			Subject
			<input class={field} bind:value={draft.subject} required />
		</label>
		<label class="flex flex-col gap-1 text-sm font-semibold">
			Email
			<textarea
				class="w-full rounded-sm border border-control bg-surface px-2.5 py-2 text-md text-ink"
				rows="6"
				bind:value={draft.body}
				required></textarea>
		</label>
		<div class="flex justify-end gap-2">
			<Button onclick={() => dialog?.close()}>Cancel</Button>
			<Button variant="primary" type="submit" disabled={sending}>Send</Button>
		</div>
	</form>
</dialog>
