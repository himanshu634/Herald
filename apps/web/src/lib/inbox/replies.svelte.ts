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
	/**
	 * The key went out in a POST and no answer has settled it: still out, no answer, a 5xx,
	 * or `sending`. The reply may be saved under the key with these words.
	 */
	held: boolean;
}

/**
 * Whether the body is locked. While the key is unsettled, the next press may only return the
 * reply already saved under it, with the old words. An edit would then be dropped while the
 * toast says it went. Sending again and Discard stay usable: they cannot change what was saved.
 */
export function locked(draft: Draft): boolean {
	return draft.held || draft.waiting !== null;
}

function newDraft(): Draft {
	return {
		body: '',
		key: crypto.randomUUID(),
		sending: false,
		markDone: false,
		last: null,
		problem: null,
		waiting: null,
		held: false
	};
}

/** The part of sessionStorage the desk uses, so tests can pass a fake. */
export type DraftStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
type Saved = Pick<Draft, 'body' | 'key' | 'waiting' | 'held' | 'last'>;

/** The browser's sessionStorage, or null where reading it throws (blocked storage). */
function sessionStore(): DraftStore | null {
	try {
		return globalThis.sessionStorage ?? null;
	} catch {
		return null;
	}
}

const storeKey = (workspaceId: string) => `herald:drafts:${workspaceId}`;

// Stored data may come from an older build or be edited by hand: anything that is not a
// draft is dropped. The key must survive with the body, or the restored draft would lose its
// protection against a second send.
function parseSaved(value: unknown): Saved | null {
	if (!value || typeof value !== 'object') return null;
	const v = value as Record<string, unknown>;
	if (typeof v.body !== 'string' || typeof v.key !== 'string' || v.key.length < 8) return null;
	const last = v.last as Reply | null | undefined;
	return {
		body: v.body,
		key: v.key,
		waiting: typeof v.waiting === 'string' ? v.waiting : null,
		held: v.held === true,
		last: last && typeof last === 'object' && typeof last.status === 'string' ? last : null
	};
}

export interface ReplyHooks {
	/**
	 * A reply to this email was sent: show this toast and refresh the emails. `shown` is
	 * whether the panel still shows that email; the owner may have moved on meanwhile.
	 */
	onsent: (toast: string, emailId: string, shown: boolean) => void;
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
	/**
	 * Drafts by email id. Kept when the composer closes, until sent or discarded. Each is also
	 * saved to sessionStorage, so the full-page trip to Google on Reconnect keeps it.
	 */
	drafts = $state<Record<string, Draft>>({});
	/** The replies of the email in the panel, oldest first. */
	list = $state.raw<Reply[]>([]);
	#listFor: string | null = null;

	#hooks: ReplyHooks;
	#store: DraftStore | null;

	constructor(hooks: ReplyHooks, store: DraftStore | null = sessionStore()) {
		this.#hooks = hooks;
		this.#store = store;
	}

	/** Bring back the workspace's saved drafts. Drafts already in memory win. */
	restore(workspaceId: string) {
		for (const [id, value] of Object.entries(this.#read(workspaceId))) {
			const saved = parseSaved(value);
			if (saved) this.drafts[id] ??= { ...newDraft(), ...saved };
		}
	}

	open(email: Email) {
		this.drafts[email.id] ??= newDraft();
		this.composingId = email.id;
	}

	close() {
		this.composingId = null;
	}

	discard(email: Email) {
		if (this.drafts[email.id]?.sending) return;
		delete this.drafts[email.id];
		this.#save(email);
		if (this.composingId === email.id) this.composingId = null;
	}

	/** The owner typed. Refused while the body is locked; the text area is read-only then. */
	setBody(email: Email, body: string) {
		const draft = this.drafts[email.id];
		if (!draft || draft.sending || locked(draft)) return;
		draft.body = body;
		this.#save(email);
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
		// Saved before the POST: if the page goes away while it is out, the restored draft
		// must still know the key may have been used.
		draft.held = true;
		this.#save(email);
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
				draft.held = false;
				this.#hooks.onmailbox();
			}
			this.#save(email);
			return;
		}
		this.#settle(email, reply);
		// Only for the email in the panel: the owner may have moved on while the POST was out,
		// and loading this one would put its replies under another customer's email.
		if (this.#listFor === email.id) this.load(email);
	}

	/** Apply an outcome, from the POST's answer or from a reload that found it settled. */
	#settle(email: Email, reply: Reply) {
		const draft = this.drafts[email.id];
		// A settled outcome spends the key, whichever path brought it. A new one is what lets
		// "Send again anyway" really send after an unknown outcome: the old key would only
		// return that row. A `sending` answer keeps it, so the next press gets that row back
		// rather than a second email; see `spendsKey`.
		if (draft && spendsKey(reply)) Object.assign(draft, { key: crypto.randomUUID(), held: false });
		if (reply.status === 'sending') {
			// Another request with this key is still out. Wait for its reply.status event.
			if (draft) Object.assign(draft, { sending: false, waiting: reply.id });
			this.#save(email);
			return;
		}
		if (reply.status === 'sent') {
			const done = draft?.markDone ?? false;
			delete this.drafts[email.id];
			this.#save(email);
			// Read before the composer closes: the page then falls back to another email.
			const shown = this.#listFor === email.id;
			if (this.composingId === email.id) this.composingId = null;
			this.#hooks.onsent(sentToast(reply.to_address, done), email.id, shown);
			return;
		}
		// Not sent, or not confirmed: the draft stays in the box with the outcome under it.
		if (draft) Object.assign(draft, { sending: false, waiting: null, last: reply });
		this.#save(email);
		if (reply.status === 'not_sent') this.#hooks.onmailbox();
	}

	// Every read and write is wrapped: blocked or full storage must leave the drafts in memory
	// working, never fail a send.
	#read(workspaceId: string): Record<string, unknown> {
		try {
			const raw = this.#store?.getItem(storeKey(workspaceId));
			const map: unknown = raw ? JSON.parse(raw) : null;
			return map && typeof map === 'object' ? (map as Record<string, unknown>) : {};
		} catch {
			return {};
		}
	}

	/** Write the email's draft as it is now, or remove it when there is none. */
	#save(email: Email) {
		if (!this.#store) return;
		const map = this.#read(email.workspace_id);
		const draft = this.drafts[email.id];
		if (draft) {
			const { body, key, waiting, held, last } = draft;
			map[email.id] = { body, key, waiting, held, last } satisfies Saved;
		} else delete map[email.id];
		try {
			const name = storeKey(email.workspace_id);
			if (Object.keys(map).length) this.#store.setItem(name, JSON.stringify(map));
			else this.#store.removeItem(name);
		} catch {
			// Memory still has the draft; only a reload would lose it.
		}
	}
}
