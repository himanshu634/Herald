import { describe, expect, it } from 'vitest';
import { parseTheme } from './prefs.svelte';

describe('parseTheme', () => {
	it('keeps a known theme', () => {
		expect(parseTheme('light')).toBe('light');
		expect(parseTheme('dark')).toBe('dark');
		expect(parseTheme('system')).toBe('system');
	});

	it('falls back to the system setting for anything else', () => {
		expect(parseTheme(null)).toBe('system');
		expect(parseTheme('sepia')).toBe('system');
	});
});
