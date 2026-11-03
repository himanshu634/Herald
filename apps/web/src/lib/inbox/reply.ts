// Reply logic with no UI: whether the owner can reply to an email, where the reply goes, and
// the words for every state a reply can be in. The copy is fixed by the owner-replies plan.
import { ApiError, type Email, type Mailbox, type Reply } from '#lib/api/client.js';
import type { IconName } from '#lib/ui/Icon.svelte';
import type { Tone } from '#lib/ui/tones.js';
import { formatTime } from './inbox';

export type ReplyState = 'ok' | 'no_mailbox' | 'paused' | 'disconnected' | 'reconnect';
type ReplyError = NonNullable<Reply['error']>;

export const REPLY_COPY = {
	no_mailbox: 'Replies need a connected Gmail. This email came in without one.',
	paused: 'This mailbox is paused. Resume it to reply.',
	disconnected: 'This mailbox is disconnected. Connect Gmail again to reply.',
	reconnect:
		"Herald can read this mailbox but can't send from it yet. Reconnect Gmail and allow sending.",
	to: (to: string) => `To: ${to}`,
	toReplyTo: (replyTo: string, sender: string) =>
		`To: ${replyTo} (the email asked for replies here; it came from ${sender})`,
	sending: 'Sending…',
	sent: (to: string, time: string) => `Sent to ${to}, ${time}.`,
	not_sent: 'Not sent. Nothing reached the customer.',
	errors: {
		rate_limited: 'Gmail asked Herald to slow down. Try again in a minute.',
		auth: 'Gmail access has ended. Reconnect Gmail.',
		send_not_allowed: "Gmail didn't allow sending. Reconnect Gmail and allow sending.",
		rejected: 'Gmail refused this message.'
	} satisfies Partial<Record<ReplyError, string>>,
	unknown:
		"Herald couldn't confirm this was sent. Check Gmail's Sent folder before you send it again.",
	toast: (to: string, done: boolean) => (done ? `Sent to ${to} and marked done` : `Sent to ${to}`),
	// Not in the plan's list: a refusal or a lost answer has no reply row to describe.
	already_sending: 'Another reply to this email is still sending. Wait for it, then try again.',
	no_answer:
		'Herald’s server didn’t answer. Your draft is kept; sending it again can’t send twice.',
	refused: 'Herald couldn’t send this reply. Your draft is kept.'
} as const;

/**
 * Whether the owner can reply from the mailbox the email came in on. The list from
 * GET /mailboxes includes disconnected rows, so a missing row means the mailbox is gone.
 */
export function replyState(email: Email, mailboxes: Mailbox[]): ReplyState {
	const mailbox = mailboxes.find((m) => m.id === email.mailbox_id);
	if (!email.mailbox_id || !mailbox) return 'no_mailbox';
	if (mailbox.status === 'paused') return 'paused';
	if (mailbox.status === 'disconnected') return 'disconnected';
	if (mailbox.status === 'needs_reauth' || !mailbox.can_send) return 'reconnect';
	return 'ok';
}

export interface Look {
	tone: Tone;
	icon: IconName;
}

/** How each line looks. Only a reconnect asks the owner to act, so only it is a warning. */
export const STATE_LOOK: Record<Exclude<ReplyState, 'ok'>, Look> = {
	no_mailbox: { tone: 'neutral', icon: 'link' },
	paused: { tone: 'neutral', icon: 'link' },
	disconnected: { tone: 'neutral', icon: 'link' },
	reconnect: { tone: 'warning', icon: 'link' }
};

export const STATUS_LOOK: Record<Reply['status'], Look> = {
	sending: { tone: 'neutral', icon: 'send' },
	sent: { tone: 'success', icon: 'check' },
	not_sent: { tone: 'danger', icon: 'close' },
	unknown: { tone: 'warning', icon: 'alert' }
};

/** The mailbox a reply to this email goes out from, if it still exists. */
export function replyMailbox(email: Email, mailboxes: Mailbox[]): Mailbox | undefined {
	return email.mailbox_id ? mailboxes.find((m) => m.id === email.mailbox_id) : undefined;
}

/**
 * Where the server will send the reply. Mirrors `_recipient` in replies.py: Reply-To only when
 * it is one plain address, else the sender. If the two drift apart, the To line shows one
 * address while the mail goes to another, so change both together.
 */
export function recipient(email: Email): string {
	const replyTo = email.reply_to;
	if (!replyTo || /[\s\p{C}<>,;:()[\]]/u.test(replyTo)) return email.sender;
	const [local, domain, ...rest] = replyTo.split('@');
	return local && domain && !rest.length ? replyTo : email.sender;
}

/** "To: …", saying so when Reply-To sends the reply somewhere other than the sender. */
export function toLine(email: Email): string {
	const to = recipient(email);
	return to === email.sender ? REPLY_COPY.to(to) : REPLY_COPY.toReplyTo(to, email.sender);
}

/** The subject the server gives a reply: "Re: " once, never "Re: Re: ". */
export function replySubject(subject: string): string {
	return subject.toLowerCase().startsWith('re:') ? subject : `Re: ${subject}`;
}

export function replyNotice(reply: Reply): string {
	switch (reply.status) {
		case 'sending':
			return REPLY_COPY.sending;
		case 'sent':
			return REPLY_COPY.sent(reply.to_address, formatTime(reply.sent_at ?? reply.created_at));
		case 'not_sent': {
			const line = reply.error && reply.error !== 'unknown' ? REPLY_COPY.errors[reply.error] : null;
			return line ? `${REPLY_COPY.not_sent} ${line}` : REPLY_COPY.not_sent;
		}
		case 'unknown':
			return REPLY_COPY.unknown;
	}
}

export function sentToast(to: string, done: boolean): string {
	return REPLY_COPY.toast(to, done);
}

/**
 * Whether a failed POST keeps the draft's client_key for the owner's next press.
 *
 * A 4xx is the server's answer about this key: it refused before saving anything, so a new key
 * is safe. No answer (fetch threw) or a 5xx (a crash, or a proxy timing out while the API waits
 * on Gmail) says nothing: the reply may exist and may have gone. Sending again with the same
 * key gets that row back from the server instead of a second email. Never resend on our own:
 * only the owner's press sends.
 */
export function keepsKey(error: unknown): boolean {
	return !(error instanceof ApiError) || error.status >= 500;
}

/** The line for a POST that saved no reply, or none we know of. */
export function failedCopy(error: unknown): string {
	if (keepsKey(error)) return REPLY_COPY.no_answer;
	const detail = error instanceof ApiError ? error.detail : null;
	if (detail === 'already_sending') return REPLY_COPY.already_sending;
	if (detail === 'no_mailbox') return REPLY_COPY.no_mailbox;
	if (detail === 'send_not_allowed') return REPLY_COPY.reconnect;
	return REPLY_COPY.refused;
}
