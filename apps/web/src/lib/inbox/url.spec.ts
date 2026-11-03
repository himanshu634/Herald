import { describe, expect, it } from 'vitest';
import { viewFrom, withoutCallback } from './url';

describe('viewFrom', () => {
	it('keeps a known view', () => {
		expect(viewFrom('closed')).toBe('closed');
	});

	it('falls back to Needs you for anything else', () => {
		expect(viewFrom('archive')).toBe('needs-you');
		expect(viewFrom('')).toBe('needs-you');
	});
});

describe('withoutCallback', () => {
	it('is null when the callback said nothing', () => {
		expect(withoutCallback('?view=all&q=shoes')).toBeNull();
		expect(withoutCallback('')).toBeNull();
	});

	it('drops the callback answer and keeps the rest', () => {
		expect(withoutCallback('?workspace=w1&mailbox_connected=1')).toBe('?workspace=w1');
		expect(withoutCallback('?workspace=w1&mailbox_error=access_denied&view=all')).toBe(
			'?workspace=w1&view=all'
		);
	});

	it('leaves an empty query when only the answer was there', () => {
		expect(withoutCallback('?mailbox_connected=1')).toBe('');
	});
});
