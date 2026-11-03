<script lang="ts">
	import type { Email, Reply } from '#lib/api/client.js';
	import { Button } from '#lib/ui/index.js';
	import { formatTime, senderName, tidyBody } from './inbox';
	import ReplyLine from './ReplyLine.svelte';
	import {
		REPLY_COPY,
		STATE_LOOK,
		STATUS_LOOK,
		replyNotice,
		replySubject,
		toLine,
		type ReplyState
	} from './reply';

	// The composer. It takes the list's place while the panel stays beside it with the notes.
	let {
		email,
		from,
		state,
		body = $bindable(),
		sending,
		waiting,
		lockHint,
		last,
		problem,
		connecting,
		onsend,
		onclose,
		ondiscard,
		onreconnect
	}: {
		email: Email;
		/** The mailbox address the reply goes out from. */
		from: string | undefined;
		state: ReplyState;
		body: string;
		/** A POST is out: the buttons wait for it. */
		sending: boolean;
		/** The server said the reply is still sending. Shown, but the buttons stay on. */
		waiting: boolean;
		/**
		 * The line saying why the body can't change while the draft's key is unsettled, or
		 * null when it can. Send and Discard still run while it is locked.
		 */
		lockHint: string | null;
		/** The last outcome that kept the draft here: not sent, or not confirmed. */
		last: Reply | null;
		/** A send that saved no reply: refused, or no answer. */
		problem: string | null;
		connecting: boolean;
		onsend: (markDone: boolean) => void;
		onclose: () => void;
		ondiscard: () => void;
		onreconnect: () => void;
	} = $props();

	// The server's address for the reply, so the box names whoever the mail really goes to.
	const to = $derived(email.reply_address);
	const name = $derived(senderName(to) || to);
	const can = $derived(state === 'ok' && !sending && !!body.trim());
	// After an unknown outcome the customer may have the email. A second send is a deliberate
	// click on a plain button, never the primary or the shortcut.
	const unsure = $derived(last?.status === 'unknown');
	const mac = /Mac|iPhone|iPad/.test(navigator.userAgent);

	// Esc and ⌘↵ work wherever focus is, the text area included, so they live here rather
	// than in the page's shortcuts, which ignore keys typed into fields.
	function onkeydown(event: KeyboardEvent) {
		if (event.defaultPrevented || (event.target as HTMLElement).closest('dialog[open]')) return;
		if (event.key === 'Escape') {
			event.preventDefault();
			onclose();
		} else if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
			event.preventDefault();
			if (can && !unsure) onsend(true);
		}
	}

	const focus = (node: HTMLTextAreaElement) => node.focus();
</script>

<svelte:window {onkeydown} />

<section
	aria-labelledby="reply-title"
	class="flex flex-1 flex-col rounded-lg border border-line bg-surface"
>
	<header
		class="flex flex-wrap items-center justify-between gap-3 border-b border-dashed border-line-dashed px-5 py-3"
	>
		<h2 id="reply-title" class="text-lg font-extrabold">Reply to {name}</h2>
		<Button variant="quiet" size="sm" kbd="Esc" onclick={onclose}>Back to the list</Button>
	</header>

	<div class="flex flex-1 flex-col gap-3 px-5 py-4">
		<figure class="rounded-xs border-l-2 border-line-strong bg-sunken px-3 py-2">
			<figcaption class="mb-1 text-xs font-semibold text-muted">
				{name} wrote, {formatTime(email.received_at)}
			</figcaption>
			<blockquote class="max-h-40 overflow-y-auto text-sm whitespace-pre-line text-body">
				{tidyBody(email.body)}
			</blockquote>
		</figure>

		<div class="flex flex-col gap-1 text-sm">
			<p class="font-semibold wrap-anywhere">{toLine(email)}</p>
			<p class="text-muted">{replySubject(email.subject)}</p>
		</div>

		<label class="sr-only" for="reply-body">Your reply to {name}</label>
		<textarea
			id="reply-body"
			bind:value={body}
			{@attach focus}
			readonly={sending || lockHint !== null}
			aria-describedby={lockHint && !sending ? 'reply-locked' : undefined}
			maxlength={20000}
			rows="9"
			class="field-sizing-content min-h-48 flex-1 resize-none rounded-sm border border-control bg-surface px-2.5 py-2 text-md leading-snug focus:border-ink"
		></textarea>
		{#if lockHint && !sending}
			<p id="reply-locked" class="text-xs text-muted">{lockHint}</p>
		{/if}
		{#if from}
			<p class="text-xs text-muted">
				Plain text. It goes from {from} into {name}'s Gmail thread.
			</p>
		{/if}

		{#if state !== 'ok'}
			<ReplyLine look={STATE_LOOK[state]} text={REPLY_COPY[state]}>
				{#if state === 'reconnect'}
					<Button size="sm" disabled={connecting} onclick={onreconnect}>Reconnect Gmail</Button>
				{/if}
			</ReplyLine>
		{:else if sending}
			<ReplyLine look={STATUS_LOOK.sending} text={REPLY_COPY.sending} />
		{:else if problem}
			<ReplyLine look={STATUS_LOOK.not_sent} text={problem} alert />
		{:else if waiting}
			<ReplyLine look={STATUS_LOOK.sending} text={REPLY_COPY.sending} />
		{:else if last}
			<ReplyLine look={STATUS_LOOK[last.status]} text={replyNotice(last)} alert />
		{/if}
	</div>

	<footer
		class="flex flex-wrap items-center gap-2 border-t border-dashed border-line-dashed px-5 py-4"
	>
		{#if unsure}
			<Button disabled={!can} onclick={() => onsend(false)}>Send again anyway</Button>
		{:else}
			<Button
				variant="primary"
				kbd={mac ? '⌘↵' : 'Ctrl ↵'}
				disabled={!can}
				onclick={() => onsend(true)}>Send and mark done</Button
			>
			<Button disabled={!can} onclick={() => onsend(false)}>Send</Button>
		{/if}
		<button
			type="button"
			class="ml-1 cursor-pointer text-sm font-bold text-ink underline underline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
			disabled={sending}
			onclick={ondiscard}>Discard</button
		>
	</footer>
</section>
