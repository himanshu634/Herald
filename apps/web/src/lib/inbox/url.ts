// What the inbox keeps on the URL, so a reload, the back button or a shared link opens the
// same business, view, filters and email. Values at their default stay off the URL.
import { createSearchParamsSchema } from 'runed/kit';
import { VIEWS, type ViewId } from './inbox.js';

export const inboxParams = createSearchParamsSchema({
	// Named `workspace` because the Gmail callback already sends the owner back with it.
	workspace: { type: 'string', default: '' },
	view: { type: 'string', default: 'alerts' },
	q: { type: 'string', default: '' },
	urgent: { type: 'boolean', default: false },
	email: { type: 'string', default: '' }
});

/**
 * A view id from the URL. Anything hand-typed or out of date, such as the old `needs-you`,
 * falls back to the alert desk.
 */
export function viewFrom(value: string): ViewId {
	return VIEWS.find((v) => v.id === value)?.id ?? 'alerts';
}

// The Gmail callback's one-off answer. Read once on load, then dropped so a reload doesn't
// show the same notice again.
const CALLBACK_KEYS = ['mailbox_error', 'mailbox_connected'];

/** The query without the callback's answer, or null when it has none. Other keys stay. */
export function withoutCallback(search: string): string | null {
	const params = new URLSearchParams(search);
	if (!CALLBACK_KEYS.some((key) => params.has(key))) return null;
	for (const key of CALLBACK_KEYS) params.delete(key);
	const rest = params.toString();
	return rest ? `?${rest}` : '';
}
