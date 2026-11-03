import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './client';

afterEach(() => vi.unstubAllGlobals());

describe('api client', () => {
	it('calls the workspace-scoped route through the /api prefix', async () => {
		const fetch = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
		vi.stubGlobal('fetch', fetch);
		expect(await api.listEmails('ws1')).toEqual([]);
		expect(fetch.mock.calls[0][0]).toBe('/api/workspaces/ws1/emails');
	});

	it('throws with the status on an error response', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 409 })));
		await expect(api.act('ws1', 'e1', 'not-urgent')).rejects.toThrow('409 nope');
	});
});
