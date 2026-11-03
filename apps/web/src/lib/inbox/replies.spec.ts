import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, type Email, type Reply } from '#lib/api/client.js';

const api = vi.hoisted(() => ({ reply: vi.fn(), replies: vi.fn() }));
vi.mock('#lib/api/client.js', async (actual) => ({
	...(await actual<typeof import('#lib/api/client.js')>()),
	api
}));

const { ReplyDesk, locked } = await import('./replies.svelte');

const email = (id: string) => ({ id, workspace_id: 'w1' }) as Email;

function reply(over: Partial<Reply> = {}): Reply {
	return {
		id: 'r1',
		email_id: 'a',
		to_address: 'arjun@outlook.com',
		subject: 'Re: x',
		body: 'Hi',
		status: 'sent',
		error: null,
		created_at: '2026-11-03T09:10:00Z',
		sent_at: '2026-11-03T09:11:00Z',
		...over
	};
}

function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((r) => (resolve = r));
	return { promise, resolve };
}

/** sessionStorage's three calls, over a Map. */
function fakeStore() {
	const items = new Map<string, string>();
	return {
		items,
		getItem: (k: string) => items.get(k) ?? null,
		setItem: (k: string, v: string) => void items.set(k, v),
		removeItem: (k: string) => void items.delete(k)
	};
}

function make(store: ReturnType<typeof fakeStore> | null = fakeStore()) {
	const hooks = { onsent: vi.fn(), onmailbox: vi.fn(), onerror: vi.fn() };
	const desk = new ReplyDesk(hooks, store);
	desk.open(email('a'));
	desk.setBody(email('a'), 'Hi');
	return { desk, hooks, store };
}

beforeEach(() => {
	api.reply.mockReset();
	api.replies.mockReset();
	api.replies.mockResolvedValue([]);
});

describe('ReplyDesk.send', () => {
	it('keeps the key and the box usable while the server says the reply is sending', async () => {
		const { desk } = make();
		const key = desk.drafts.a.key;
		api.reply.mockResolvedValue(reply({ status: 'sending', sent_at: null }));

		await desk.send(email('a'), false);

		expect(desk.drafts.a.key).toBe(key);
		expect(desk.drafts.a.sending).toBe(false);
		expect(desk.drafts.a.waiting).toBe('r1');

		// The next press resends with the same key, so the server can expire a dead row.
		api.reply.mockResolvedValue(reply({ status: 'unknown', error: 'unknown', sent_at: null }));
		await desk.send(email('a'), false);

		expect(api.reply).toHaveBeenLastCalledWith('w1', 'a', {
			body: 'Hi',
			client_key: key,
			mark_done: false
		});
		expect(desk.drafts.a.waiting).toBeNull();
		expect(desk.drafts.a.key).not.toBe(key);
	});

	it('spends the key when a reload finds the waited-on reply settled', async () => {
		// The reply.status event path: the page reloads the list and the draft settles there.
		const { desk } = make();
		const key = desk.drafts.a.key;
		api.reply.mockResolvedValue(reply({ status: 'sending', sent_at: null }));
		await desk.send(email('a'), false);
		await new Promise((r) => setTimeout(r));
		expect(desk.drafts.a.key).toBe(key);

		api.replies.mockResolvedValue([reply({ status: 'unknown', error: 'unknown', sent_at: null })]);
		await desk.load(email('a'));

		expect(desk.drafts.a.waiting).toBeNull();
		expect(desk.drafts.a.last?.status).toBe('unknown');
		// "Send again anyway" must really send: a new key, not the one that returns the row.
		expect(desk.drafts.a.key).not.toBe(key);
		api.reply.mockResolvedValue(reply());
		await desk.send(email('a'), false);
		expect(api.reply.mock.lastCall?.[2].client_key).not.toBe(key);
	});

	it('lets the owner discard a draft that waits on a sending reply', async () => {
		const { desk } = make();
		api.reply.mockResolvedValue(reply({ status: 'sending', sent_at: null }));
		await desk.send(email('a'), false);

		desk.discard(email('a'));

		expect(desk.drafts.a).toBeUndefined();
	});

	it('leaves the panel alone when it moved to another email while the POST was out', async () => {
		const { desk } = make();
		await desk.load(email('a'));
		const answer = deferred<Reply>();
		api.reply.mockReturnValue(answer.promise);

		const sending = desk.send(email('a'), false);
		api.replies.mockResolvedValue([reply({ id: 'b1', email_id: 'b' })]);
		await desk.load(email('b'));
		answer.resolve(reply({ status: 'not_sent', error: 'rejected', sent_at: null }));
		await sending;
		await new Promise((r) => setTimeout(r));

		expect(api.replies).toHaveBeenLastCalledWith('w1', 'b');
		expect(desk.list.map((r) => r.id)).toEqual(['b1']);
	});

	it('reloads the panel when it still shows the answered email', async () => {
		const { desk } = make();
		await desk.load(email('a'));
		api.reply.mockResolvedValue(reply({ status: 'not_sent', error: 'rejected', sent_at: null }));
		api.replies.mockResolvedValue([reply({ status: 'not_sent', error: 'rejected' })]);

		await desk.send(email('a'), false);
		await new Promise((r) => setTimeout(r));

		expect(desk.list.map((r) => r.status)).toEqual(['not_sent']);
	});

	it('names the answered email when a reply is sent', async () => {
		const { desk, hooks } = make();
		api.reply.mockResolvedValue(reply());

		await desk.send(email('a'), true);

		expect(hooks.onsent).toHaveBeenCalledWith(
			'Sent to arjun@outlook.com and marked done',
			'a',
			false
		);
		expect(desk.drafts.a).toBeUndefined();
		expect(desk.composingId).toBeNull();
	});
});

describe('ReplyDesk pinning a sent email', () => {
	it('says the panel shows the email when the answer comes back', async () => {
		const { desk, hooks } = make();
		await desk.load(email('a'));
		api.reply.mockResolvedValue(reply());

		await desk.send(email('a'), true);

		expect(hooks.onsent).toHaveBeenCalledWith(expect.any(String), 'a', true);
	});

	it('says it does not once the owner moved on while the POST was out', async () => {
		const { desk, hooks } = make();
		await desk.load(email('a'));
		const answer = deferred<Reply>();
		api.reply.mockReturnValue(answer.promise);

		const sending = desk.send(email('a'), true);
		await desk.load(email('b'));
		answer.resolve(reply());
		await sending;

		expect(hooks.onsent).toHaveBeenCalledWith(expect.any(String), 'a', false);
	});
});

describe('ReplyDesk locking the body while the key is unsettled', () => {
	it('locks it when no answer came back, and keeps the key', async () => {
		const { desk } = make();
		const key = desk.drafts.a.key;
		api.reply.mockRejectedValue(new TypeError('Failed to fetch'));

		await desk.send(email('a'), false);

		expect(locked(desk.drafts.a)).toBe(true);
		expect(desk.drafts.a.key).toBe(key);
		desk.setBody(email('a'), 'Hi, edited');
		expect(desk.drafts.a.body).toBe('Hi');
	});

	it('locks it after a 5xx', async () => {
		const { desk } = make();
		api.reply.mockRejectedValue(new ApiError(502, 'Bad Gateway'));

		await desk.send(email('a'), false);

		expect(locked(desk.drafts.a)).toBe(true);
	});

	it('locks it while the server says the reply is sending', async () => {
		const { desk } = make();
		api.reply.mockResolvedValue(reply({ status: 'sending', sent_at: null }));

		await desk.send(email('a'), false);

		expect(locked(desk.drafts.a)).toBe(true);
	});

	it('leaves it open after a refusal: nothing was saved under the key', async () => {
		const { desk } = make();
		api.reply.mockRejectedValue(new ApiError(409, '{"detail":"already_sending"}'));

		await desk.send(email('a'), false);

		expect(locked(desk.drafts.a)).toBe(false);
		desk.setBody(email('a'), 'Hi, edited');
		expect(desk.drafts.a.body).toBe('Hi, edited');
	});

	it('unlocks it once a resend gets a final status', async () => {
		for (const status of ['not_sent', 'unknown'] as const) {
			const { desk } = make();
			api.reply.mockRejectedValueOnce(new TypeError('Failed to fetch'));
			await desk.send(email('a'), false);
			expect(locked(desk.drafts.a)).toBe(true);

			api.reply.mockResolvedValueOnce(reply({ status, error: 'unknown', sent_at: null }));
			await desk.send(email('a'), false);

			expect(locked(desk.drafts.a), status).toBe(false);
		}
	});

	it('unlocks it when a reload finds the waited-on reply settled', async () => {
		const { desk } = make();
		api.reply.mockResolvedValue(reply({ status: 'sending', sent_at: null }));
		await desk.send(email('a'), false);
		await new Promise((r) => setTimeout(r));

		api.replies.mockResolvedValue([reply({ status: 'unknown', error: 'unknown', sent_at: null })]);
		await desk.load(email('a'));

		expect(locked(desk.drafts.a)).toBe(false);
	});
});

describe('ReplyDesk saving drafts across a page load', () => {
	it('restores the body, the key and the wait in a new page', async () => {
		const { desk, store } = make();
		api.reply.mockResolvedValue(reply({ status: 'sending', sent_at: null }));
		await desk.send(email('a'), false);
		const { key } = desk.drafts.a;

		// The page went to Google and back: a new desk over the same storage.
		const after = new ReplyDesk({ onsent: vi.fn(), onmailbox: vi.fn(), onerror: vi.fn() }, store);
		after.restore('w1');

		expect(after.drafts.a).toMatchObject({ body: 'Hi', key, waiting: 'r1', sending: false });
		expect(locked(after.drafts.a)).toBe(true);
	});

	it('keeps a draft locked after no answer, so a reload cannot unlock it', async () => {
		const { desk, store } = make();
		api.reply.mockRejectedValue(new TypeError('Failed to fetch'));
		await desk.send(email('a'), false);

		const after = new ReplyDesk({ onsent: vi.fn(), onmailbox: vi.fn(), onerror: vi.fn() }, store);
		after.restore('w1');

		expect(after.drafts.a.key).toBe(desk.drafts.a.key);
		expect(locked(after.drafts.a)).toBe(true);
	});

	it('saves each edit, under the workspace', () => {
		const { desk, store } = make();
		desk.setBody(email('a'), 'Hi Arjun');

		expect(JSON.parse(store!.items.get('herald:drafts:w1')!).a.body).toBe('Hi Arjun');
	});

	it('forgets a draft once it is sent or discarded', async () => {
		const { desk, store } = make();
		desk.open(email('b'));
		desk.setBody(email('b'), 'Hello');
		api.reply.mockResolvedValue(reply());

		await desk.send(email('a'), false);
		expect(Object.keys(JSON.parse(store!.items.get('herald:drafts:w1')!))).toEqual(['b']);

		desk.discard(email('b'));
		expect(store!.items.has('herald:drafts:w1')).toBe(false);
	});

	it('drops stored entries that are not drafts', () => {
		const store = fakeStore();
		store.setItem('herald:drafts:w1', JSON.stringify({ a: { body: 'Hi' }, b: 'junk' }));
		const desk = new ReplyDesk({ onsent: vi.fn(), onmailbox: vi.fn(), onerror: vi.fn() }, store);

		desk.restore('w1');

		expect(desk.drafts).toEqual({});
	});

	it('keeps drafts in memory when storage throws', async () => {
		const broken = {
			getItem: () => {
				throw new Error('SecurityError');
			},
			setItem: () => {
				throw new Error('QuotaExceededError');
			},
			removeItem: () => {
				throw new Error('SecurityError');
			}
		};
		const hooks = { onsent: vi.fn(), onmailbox: vi.fn(), onerror: vi.fn() };
		const desk = new ReplyDesk(hooks, broken);
		desk.restore('w1');
		desk.open(email('a'));
		desk.setBody(email('a'), 'Hi');
		api.reply.mockResolvedValue(reply());

		expect(desk.drafts.a.body).toBe('Hi');
		await desk.send(email('a'), false);
		expect(hooks.onsent).toHaveBeenCalled();
	});
});
