// The owner's display choices: theme and whether the rail shows labels. Kept in this browser
// only, so each read and write tolerates storage that is blocked or full.

export const THEMES = ['system', 'light', 'dark'] as const;
export type Theme = (typeof THEMES)[number];

// app.html reads THEME_KEY before the page paints. Change the key in both places.
export const THEME_KEY = 'herald.theme';
export const RAIL_KEY = 'herald.rail';

export function parseTheme(value: string | null): Theme {
	return THEMES.includes(value as Theme) ? (value as Theme) : 'system';
}

function read(key: string): string | null {
	try {
		return localStorage.getItem(key);
	} catch {
		return null;
	}
}

function write(key: string, value: string) {
	try {
		localStorage.setItem(key, value);
	} catch {
		// Private mode or blocked storage: the choice lasts until the tab closes.
	}
}

// "system" removes the attribute: tokens.css then follows prefers-color-scheme.
function apply(theme: Theme) {
	if (theme === 'system') delete document.documentElement.dataset.theme;
	else document.documentElement.dataset.theme = theme;
}

class Prefs {
	theme = $state<Theme>(parseTheme(read(THEME_KEY)));
	railOpen = $state(read(RAIL_KEY) === 'open');

	setTheme(theme: Theme) {
		this.theme = theme;
		apply(theme);
		write(THEME_KEY, theme);
	}

	toggleRail() {
		this.railOpen = !this.railOpen;
		write(RAIL_KEY, this.railOpen ? 'open' : 'closed');
	}
}

export const prefs = new Prefs();
