// Mailbox rules for the inbox: when a business must connect first, what the header chip says,
// and the plain words for each answer the OAuth callback sends back.
import type { Mailbox, Workspace } from '#lib/api/client.js';

/** Mailboxes that still feed the business. A disconnected one is kept only as history. */
export function liveMailboxes(mailboxes: Mailbox[]): Mailbox[] {
	return mailboxes.filter((m) => m.status !== 'disconnected');
}

/**
 * True when the business stays closed until a mailbox is connected. Only the seeded demo
 * opens without one: every real business is about its own customers' mail.
 */
export function needsMailbox(workspace: Workspace, mailboxes: Mailbox[]): boolean {
	return !workspace.demo && liveMailboxes(mailboxes).length === 0;
}

export interface Notice {
	tone: 'ok' | 'danger';
	title: string;
	text: string;
	/** Show "Try again", which starts the same connect. */
	retry: boolean;
}

// One sentence and one action per callback error. The code itself never shows.
const ERRORS: Record<string, Omit<Notice, 'tone'>> = {
	access_denied: {
		title: 'Gmail isn’t connected.',
		text: 'You didn’t allow access on Google’s screen, so nothing was connected.',
		retry: true
	},
	invalid_state: {
		title: 'Gmail isn’t connected.',
		text: 'The connect link was more than 10 minutes old or came from another tab.',
		retry: true
	},
	authorization_failed: {
		title: 'Gmail isn’t connected.',
		text: 'Google didn’t finish the sign-in.',
		retry: true
	},
	no_refresh_token: {
		title: 'Gmail isn’t connected.',
		text: 'Google didn’t give Herald lasting access. Remove Herald under Third-party access in your Google account, then connect again.',
		retry: true
	},
	mailbox_in_use: {
		title: 'Gmail isn’t connected.',
		text: 'That address already feeds another business in Herald, and one mailbox serves one business. Disconnect it there first, or connect another address.',
		retry: false
	},
	provider_unavailable: {
		title: 'Gmail isn’t connected.',
		text: 'Gmail isn’t set up on this Herald server.',
		retry: false
	},
	provider_error: {
		title: 'Gmail isn’t connected.',
		text: 'Gmail refused the connection. It may be turned off for this Google account.',
		retry: true
	}
};

export interface Return {
	/** The business the connect started from. Missing when the callback could not trust it. */
	workspace: string | null;
	notice: Notice | null;
}

/** Read what the OAuth callback put on the URL. */
export function readReturn(params: Pick<URLSearchParams, 'get' | 'has'>): Return {
	const workspace = params.get('workspace');
	const error = params.get('mailbox_error');
	if (error !== null) {
		const known = ERRORS[error] ?? ERRORS.provider_error;
		return { workspace, notice: { tone: 'danger', ...known } };
	}
	if (params.has('mailbox_connected')) {
		return {
			workspace,
			notice: {
				tone: 'ok',
				title: 'Gmail is connected.',
				// Matches the connector's first sync: inbox mail newer than 2 days, at most 50.
				text: 'Herald is reading the last 2 days of mail, up to 50 emails. They show up here as each one is read.',
				retry: false
			}
		};
	}
	return { workspace, notice: null };
}

/** "just now", "4 min ago", "3 h ago", "2 days ago". */
export function ago(iso: string | null | undefined, now: Date = new Date()): string | null {
	if (!iso) return null;
	const minutes = Math.floor((now.getTime() - new Date(iso).getTime()) / 60_000);
	if (minutes < 1) return 'just now';
	if (minutes < 60) return `${minutes} min ago`;
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return `${hours} h ago`;
	const days = Math.floor(hours / 24);
	return days === 1 ? 'yesterday' : `${days} days ago`;
}
