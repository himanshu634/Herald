// Reply logic with no UI: whether the owner can reply to an email, where the reply goes, and
// the words for every state a reply can be in. The copy is fixed by the owner-replies plan.
import {
	ApiError,
	type Email,
	type EmailStatus,
	type Mailbox,
	type Reply
} from '#lib/api/client.js';
import type { IconName } from '#lib/ui/Icon.svelte';
import type { Tone } from '#lib/ui/tones.js';
import { formatTime } from './inbox';

export type ReplyState =
	'ok' | 'no_mailbox' | 'paused' | 'disconnected' | 'reconnect' | 'no_recipient';
type ReplyError = NonNullable<Reply['error']>;

export const REPLY_COPY = {
	no_mailbox: 'Replies need a connected Gmail. This email came in without one.',
	paused: 'This mailbox is paused. Resume it to reply.',
	disconnected: 'This mailbox is disconnected. Connect Gmail again to reply.',
	reconnect:
		"Herald can read this mailbox but can't send from it yet. Reconnect Gmail and allow sending.",
	no_recipient: "Herald can't tell who to reply to for this email.",
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
	refused: 'Herald couldn’t send this reply. Your draft is kept.',
	// The draft's key went out and no answer settled it. An edit now could be dropped: the
	// next press may only return the reply that was saved with the old words.
	locked: {
		// The server named a reply that is still sending; its reply.status event settles it.
		checking: 'Herald is checking whether this was sent. You can edit it once that’s settled.',
		// No answer or a 5xx: nothing is watching this key. Only the owner's next Send asks the
		// server about it. After a reload this is the only line left, as `no_answer` isn't saved.
		unheard:
			'Herald didn’t hear back about this reply. Press Send again to find out whether it went; you can edit it once that’s settled.'
	}
} as const;

/**
 * Whether the owner can reply from the mailbox the email came in on. The list from
 * GET /mailboxes includes disconnected rows, so a missing row means the mailbox is gone.
 * The checks run in the server's order, so the panel names the reason a POST would get.
 */
export function replyState(email: Email, mailboxes: Mailbox[]): ReplyState {
	const mailbox = mailboxes.find((m) => m.id === email.mailbox_id);
	if (!email.mailbox_id || !mailbox) return 'no_mailbox';
	if (mailbox.status === 'paused') return 'paused';
	if (mailbox.status === 'disconnected') return 'disconnected';
	if (mailbox.status === 'needs_reauth' || !mailbox.can_send) return 'reconnect';
	// No address the server could use, or the shop's own: the reply would mail the owner.
	const to = email.reply_address.toLowerCase();
	if (!to || to === mailbox.email_address.toLowerCase()) return 'no_recipient';
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
	reconnect: { tone: 'warning', icon: 'link' },
	no_recipient: { tone: 'neutral', icon: 'info' }
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
 * "To: …", saying so when Reply-To sends the reply somewhere other than the sender. The
 * address is the server's `reply_address`, the one the send uses, never worked out here.
 */
export function toLine(email: Email): string {
	const to = email.reply_address;
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

/**
 * The toast for a sent reply. "And marked done" only when this send moved the email to done:
 * not done when the owner pressed Send (`before`), done in the refreshed list. Not from the
 * button pressed: a press that reuses an earlier key gets that earlier send's row back, and
 * the server applies only that send's mark_done. An email that was already done, or one the
 * refresh couldn't load, says only "Sent".
 */
export function sentToast(
	to: string,
	before: EmailStatus,
	after: Pick<Email, 'status'> | undefined
): string {
	return REPLY_COPY.toast(to, before !== 'done' && after?.status === 'done');
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

/**
 * Whether a 200 answer spends the draft's client_key. A settled reply does: the next press is
 * a new send. A `sending` one does not: that reply may still go out, so the next press must
 * name the same key and get that row back, never send a second email. If its process died,
 * the server turns the row unknown on the next POST for this email, with this key or a new
 * one, and reads report it as unknown once it is stale.
 */
export function spendsKey(reply: Reply): boolean {
	return reply.status !== 'sending';
}

/** The line for a POST that saved no reply, or none we know of. */
export function failedCopy(error: unknown): string {
	if (keepsKey(error)) return REPLY_COPY.no_answer;
	const detail = error instanceof ApiError ? error.detail : null;
	if (detail === 'already_sending') return REPLY_COPY.already_sending;
	if (detail === 'no_mailbox') return REPLY_COPY.no_mailbox;
	if (detail === 'send_not_allowed') return REPLY_COPY.reconnect;
	if (detail === 'no_recipient') return REPLY_COPY.no_recipient;
	return REPLY_COPY.refused;
}
