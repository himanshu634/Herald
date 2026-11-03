// The inbox's reply wiring: one draft per email, the composer that is open, sending, and the
// open email's replies. Kept out of +page.svelte so the page only connects it to the screen.
import { api, type Email, type Reply } from '#lib/api/client.js';
import { failedCopy, keepsKey, sentToast, spendsKey } from './reply';

export interface Draft {
	body: string;
	/**
	 * The draft's client_key. The server sends one key at most once, so the key lives until
	 * the server answers for it; see `keepsKey` for which failures count as no answer.
	 */
	key: string;
	/** A POST is out. The buttons and Discard wait for it. */
	sending: boolean;
	/** The button the owner pressed last, for the toast. */
	markDone: boolean;
	/** The last outcome that kept the draft: not sent, or not confirmed. */
	last: Reply | null;
	/** A send that saved no reply we know of: refused, or no answer. */
	problem: string | null;
	/**
	 * The reply the server said is still sending. Its reply.status event settles the draft.
	 * The box says "Sending…" but stays usable: a press resends with the same key, which can
	 * only return that row or expire it as unknown on the server, never send a second email.
	 */
	waiting: string | null;
}

function newDraft(): Draft {
	return {
		body: '',
		key: crypto.randomUUID(),
		sending: false,
		markDone: false,
		last: null,
		problem: null,
		waiting: null
	};
}

export interface ReplyHooks {
	/** A reply to this email was sent: show this toast and refresh the emails. */
	onsent: (toast: string, emailId: string) => void;
	/** The mailbox may have changed (refused, or Gmail took access away): refresh it. */
	onmailbox: () => void;
	onerror: (error: unknown) => void;
}

export class ReplyDesk {
	/**
	 * The email the composer is open for. Pinned by id, never "the selected email": that one
	 * changes when the list does, and the reply would then go to another customer.
	 */
	composingId = $state<string | null>(null);
	/** Drafts by email id. Kept when the composer closes, until sent or discarded. */
	drafts = $state<Record<string, Draft>>({});
	/** The replies of the email in the panel, oldest first. */
	list = $state.raw<Reply[]>([]);
	#listFor: string | null = null;

	#hooks: ReplyHooks;

	constructor(hooks: ReplyHooks) {
		this.#hooks = hooks;
	}

	open(emailId: string) {
		this.drafts[emailId] ??= newDraft();
		this.composingId = emailId;
	}

	close() {
		this.composingId = null;
	}

	discard(emailId: string) {
		if (this.drafts[emailId]?.sending) return;
		delete this.drafts[emailId];
		if (this.composingId === emailId) this.composingId = null;
	}

	/** Fetch the email's replies. Answers for an email no longer in the panel are dropped. */
	async load(email: Email) {
		const id = email.id;
		if (this.#listFor !== id) {
			this.#listFor = id;
			this.list = [];
		}
		let list: Reply[];
		try {
			list = await api.replies(email.workspace_id, id);
		} catch (e) {
			if (this.#listFor === id) this.#hooks.onerror(e);
			return;
		}
		if (this.#listFor !== id) return;
		this.list = list;
		// A draft waiting on a reply that has since settled, say while the event was missed.
		const waiting = this.drafts[id]?.waiting;
		const settled = waiting ? list.find((r) => r.id === waiting && r.status !== 'sending') : null;
		if (settled) this.#settle(email, settled);
	}

	async send(email: Email, markDone: boolean) {
		const draft = this.drafts[email.id];
		if (!draft || draft.sending || !draft.body.trim()) return;
		draft.sending = true;
		draft.markDone = markDone;
		draft.problem = null;
		let reply: Reply;
		try {
			reply = await api.reply(email.workspace_id, email.id, {
				body: draft.body,
				client_key: draft.key,
				mark_done: markDone
			});
		} catch (e) {
			draft.sending = false;
			draft.problem = failedCopy(e);
			// No answer: keep the key, so the owner's next press gets the saved reply back
			// instead of sending a second email. A refusal saved nothing, so a new key is safe.
			if (!keepsKey(e)) {
				draft.key = crypto.randomUUID();
				this.#hooks.onmailbox();
			}
			return;
		}
		// A settled answer spends the key. A new one is what lets "Send again anyway" really
		// send after an unknown outcome: the old key would only return that row. A `sending`
		// answer keeps it: only a POST with that key can expire the row if its process died.
		if (spendsKey(reply)) draft.key = crypto.randomUUID();
		this.#settle(email, reply);
		// Only for the email in the panel: the owner may have moved on while the POST was out,
		// and loading this one would put its replies under another customer's email.
		if (this.#listFor === email.id) this.load(email);
	}

	#settle(email: Email, reply: Reply) {
		const draft = this.drafts[email.id];
		if (reply.status === 'sending') {
			// Another request with this key is still out. Wait for its reply.status event.
			if (draft) Object.assign(draft, { sending: false, waiting: reply.id });
			return;
		}
		if (reply.status === 'sent') {
			const done = draft?.markDone ?? false;
			delete this.drafts[email.id];
			if (this.composingId === email.id) this.composingId = null;
			this.#hooks.onsent(sentToast(reply.to_address, done), email.id);
			return;
		}
		// Not sent, or not confirmed: the draft stays in the box with the outcome under it.
		if (draft) Object.assign(draft, { sending: false, waiting: null, last: reply });
		if (reply.status === 'not_sent') this.#hooks.onmailbox();
	}
}
