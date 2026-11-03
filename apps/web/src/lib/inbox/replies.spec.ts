import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Email, Reply } from '#lib/api/client.js';

const api = vi.hoisted(() => ({ reply: vi.fn(), replies: vi.fn() }));
vi.mock('#lib/api/client.js', async (actual) => ({
	...(await actual<typeof import('#lib/api/client.js')>()),
	api
}));

const { ReplyDesk } = await import('./replies.svelte');

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

function make() {
	const hooks = { onsent: vi.fn(), onmailbox: vi.fn(), onerror: vi.fn() };
	const desk = new ReplyDesk(hooks);
	desk.open('a');
	desk.drafts.a.body = 'Hi';
	return { desk, hooks };
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

		desk.discard('a');

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

		expect(hooks.onsent).toHaveBeenCalledWith('Sent to arjun@outlook.com and marked done', 'a');
		expect(desk.drafts.a).toBeUndefined();
		expect(desk.composingId).toBeNull();
	});
});
