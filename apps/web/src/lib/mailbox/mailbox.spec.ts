import { describe, expect, it } from 'vitest';
import type { Mailbox, Workspace } from '#lib/api/client.js';
import { ago, liveMailboxes, needsMailbox, readReturn } from './mailbox';

const workspace = (demo: boolean) => ({ id: 'w1', demo }) as Workspace;
const mailbox = (status: Mailbox['status']) => ({ id: status, status }) as Mailbox;

describe('needsMailbox', () => {
	it('closes a real business with no mailbox', () => {
		expect(needsMailbox(workspace(false), [])).toBe(true);
	});

	it('counts a disconnected mailbox as none', () => {
		expect(needsMailbox(workspace(false), [mailbox('disconnected')])).toBe(true);
	});

	it('opens once a mailbox is live, even paused or needing a reconnect', () => {
		for (const status of ['active', 'paused', 'needs_reauth'] as const) {
			expect(needsMailbox(workspace(false), [mailbox(status)])).toBe(false);
		}
	});

	it('never closes the demo', () => {
		expect(needsMailbox(workspace(true), [])).toBe(false);
	});
});

describe('liveMailboxes', () => {
	it('drops disconnected mailboxes', () => {
		const list = [mailbox('active'), mailbox('disconnected')];
		expect(liveMailboxes(list).map((m) => m.status)).toEqual(['active']);
	});
});

describe('readReturn', () => {
	it('reads a connect', () => {
		const back = readReturn(new URLSearchParams('mailbox_connected=m1&workspace=w1'));
		expect(back.workspace).toBe('w1');
		expect(back.notice?.tone).toBe('ok');
	});

	it('reads an error with its retry', () => {
		const denied = readReturn(new URLSearchParams('mailbox_error=access_denied&workspace=w1'));
		expect(denied.notice).toMatchObject({ tone: 'danger', retry: true });
		const inUse = readReturn(new URLSearchParams('mailbox_error=mailbox_in_use'));
		expect(inUse.notice?.retry).toBe(false);
		expect(inUse.workspace).toBeNull();
	});

	it('treats an unknown error as a provider error', () => {
		const back = readReturn(new URLSearchParams('mailbox_error=something_new'));
		expect(back.notice?.text).toMatch(/refused/);
	});

	it('is empty on a plain visit', () => {
		expect(readReturn(new URLSearchParams(''))).toEqual({ workspace: null, notice: null });
	});
});

describe('ago', () => {
	const now = new Date('2026-11-03T12:00:00Z');
	it('rounds to the largest unit', () => {
		expect(ago('2026-11-03T11:59:40Z', now)).toBe('just now');
		expect(ago('2026-11-03T11:56:00Z', now)).toBe('4 min ago');
		expect(ago('2026-11-03T09:00:00Z', now)).toBe('3 h ago');
		expect(ago('2026-11-02T10:00:00Z', now)).toBe('yesterday');
		expect(ago(null, now)).toBeNull();
	});
});
