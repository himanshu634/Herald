import { describe, expect, it } from 'vitest';
import { ApiError, type Email, type Mailbox, type Reply } from '#lib/api/client.js';
import { formatTime } from './inbox';
import {
	REPLY_COPY,
	failedCopy,
	keepsKey,
	replyNotice,
	replyState,
	replySubject,
	sentToast,
	spendsKey,
	toLine
} from './reply';

function email(over: Partial<Email> = {}): Email {
	return {
		id: 'e1',
		workspace_id: 'w1',
		mailbox_id: 'm1',
		sender: 'arjun.mehta@outlook.com',
		reply_to: null,
		reply_address: 'arjun.mehta@outlook.com',
		subject: 'Refund still not received',
		body: 'Body',
		thread_id: null,
		status: 'alerted',
		notes: null,
		decision: null,
		context: null,
		received_at: '2026-11-03T09:00:00Z',
		...over
	};
}

const mailbox = (status: Mailbox['status'], can_send = true, id = 'm1') =>
	({ id, status, can_send, email_address: 'meera@tripfold.in' }) as Mailbox;

function reply(over: Partial<Reply> = {}): Reply {
	return {
		id: 'r1',
		email_id: 'e1',
		to_address: 'arjun.mehta@outlook.com',
		subject: 'Re: Refund still not received',
		body: 'Hi Arjun',
		status: 'sent',
		error: null,
		created_at: '2026-11-03T09:10:00Z',
		sent_at: '2026-11-03T09:11:00Z',
		...over
	};
}

describe('replyState', () => {
	it('needs a mailbox on the email', () => {
		expect(replyState(email({ mailbox_id: null }), [mailbox('active')])).toBe('no_mailbox');
	});

	it('treats a mailbox missing from the list as none', () => {
		expect(replyState(email({ mailbox_id: 'gone' }), [mailbox('active')])).toBe('no_mailbox');
	});

	it('matches the email to its own mailbox, not the first one', () => {
		const list = [mailbox('active', true, 'other'), mailbox('paused')];
		expect(replyState(email(), list)).toBe('paused');
	});

	it('says paused and disconnected', () => {
		expect(replyState(email(), [mailbox('paused')])).toBe('paused');
		expect(replyState(email(), [mailbox('disconnected')])).toBe('disconnected');
	});

	it('asks for a reconnect when access ended or sending was never allowed', () => {
		expect(replyState(email(), [mailbox('needs_reauth')])).toBe('reconnect');
		expect(replyState(email(), [mailbox('active', false)])).toBe('reconnect');
	});

	it('lets an active mailbox that can send reply', () => {
		expect(replyState(email(), [mailbox('active')])).toBe('ok');
	});

	it('says it cannot tell who to reply to when the server has no address', () => {
		expect(replyState(email({ reply_address: '' }), [mailbox('active')])).toBe('no_recipient');
	});

	it('will not reply to the shop’s own mailbox', () => {
		const own = email({ sender: 'Meera@Tripfold.in', reply_address: 'Meera@Tripfold.in' });
		expect(replyState(own, [mailbox('active')])).toBe('no_recipient');
	});

	it('names a mailbox problem before a missing recipient, as the server does', () => {
		expect(replyState(email({ reply_address: '' }), [mailbox('active', false)])).toBe('reconnect');
	});
});

describe('replyNotice', () => {
	it('says where a sent reply went, and when', () => {
		const sent = reply();
		expect(replyNotice(sent)).toBe(
			`Sent to arjun.mehta@outlook.com, ${formatTime(sent.sent_at!)}.`
		);
		expect(replyNotice(sent)).toBe(REPLY_COPY.sent(sent.to_address, formatTime(sent.sent_at!)));
	});

	it('says sending', () => {
		expect(replyNotice(reply({ status: 'sending', sent_at: null }))).toBe('Sending…');
		expect(REPLY_COPY.sending).toBe('Sending…');
	});

	it('gives one line per reason a reply was not sent', () => {
		const lines = {
			rate_limited: 'Gmail asked Herald to slow down. Try again in a minute.',
			auth: 'Gmail access has ended. Reconnect Gmail.',
			send_not_allowed: "Gmail didn't allow sending. Reconnect Gmail and allow sending.",
			rejected: 'Gmail refused this message.'
		} as const;
		for (const [error, line] of Object.entries(lines)) {
			const notice = replyNotice(
				reply({ status: 'not_sent', error: error as Reply['error'], sent_at: null })
			);
			expect(notice).toBe(`Not sent. Nothing reached the customer. ${line}`);
			expect(notice).toBe(
				`${REPLY_COPY.not_sent} ${REPLY_COPY.errors[error as keyof typeof lines]}`
			);
		}
	});

	it('says only that nothing was sent when the reason is not known', () => {
		expect(replyNotice(reply({ status: 'not_sent', error: null, sent_at: null }))).toBe(
			'Not sent. Nothing reached the customer.'
		);
	});

	it('tells the owner to check Gmail when the outcome is unknown', () => {
		const notice = replyNotice(reply({ status: 'unknown', error: 'unknown', sent_at: null }));
		expect(notice).toBe(
			"Herald couldn't confirm this was sent. Check Gmail's Sent folder before you send it again."
		);
		expect(notice).toBe(REPLY_COPY.unknown);
	});
});

describe('the words for the states the panel shows', () => {
	it('are the plan’s', () => {
		expect(REPLY_COPY.no_mailbox).toBe(
			'Replies need a connected Gmail. This email came in without one.'
		);
		expect(REPLY_COPY.paused).toBe('This mailbox is paused. Resume it to reply.');
		expect(REPLY_COPY.disconnected).toBe(
			'This mailbox is disconnected. Connect Gmail again to reply.'
		);
		expect(REPLY_COPY.reconnect).toBe(
			"Herald can read this mailbox but can't send from it yet. Reconnect Gmail and allow sending."
		);
		expect(REPLY_COPY.no_recipient).toBe("Herald can't tell who to reply to for this email.");
	});
});

describe('the To line', () => {
	it('names the server’s reply_address when it is the sender', () => {
		expect(toLine(email())).toBe('To: arjun.mehta@outlook.com');
	});

	it('says so when the reply goes somewhere other than the sender', () => {
		const form = email({ sender: 'forms@tripfold.in', reply_address: 'neha.kapoor@yahoo.in' });
		expect(toLine(form)).toBe(
			'To: neha.kapoor@yahoo.in (the email asked for replies here; it came from forms@tripfold.in)'
		);
	});

	it('follows reply_address, not reply_to: the server decides where the mail goes', () => {
		// The server sends to a quoted local part with a comma; the line must show it too.
		const quoted = email({ reply_to: '"a,b"@yahoo.in', reply_address: '"a,b"@yahoo.in' });
		expect(toLine(quoted)).toBe(
			'To: "a,b"@yahoo.in (the email asked for replies here; it came from arjun.mehta@outlook.com)'
		);
		// A Reply-To the server will not use leaves reply_address on the sender.
		const list = email({ reply_to: 'a@x.in, b@y.in' });
		expect(toLine(list)).toBe('To: arjun.mehta@outlook.com');
	});
});

describe('replySubject', () => {
	it('adds Re: once', () => {
		expect(replySubject('Refund')).toBe('Re: Refund');
		expect(replySubject('RE: Refund')).toBe('RE: Refund');
	});
});

describe('sentToast', () => {
	it('says marked done only when this send moved the email to done', () => {
		expect(sentToast('a@x.in', 'inbox', email({ status: 'inbox' }))).toBe('Sent to a@x.in');
		expect(sentToast('a@x.in', 'inbox', email({ status: 'done' }))).toBe(
			'Sent to a@x.in and marked done'
		);
	});

	it('says only where it went when the email was already done', () => {
		expect(sentToast('a@x.in', 'done', email({ status: 'done' }))).toBe('Sent to a@x.in');
	});

	it('says only where it went when the refreshed email is not known', () => {
		expect(sentToast('a@x.in', 'inbox', undefined)).toBe('Sent to a@x.in');
	});
});

describe('keepsKey', () => {
	it('keeps the draft’s key when no answer came back', () => {
		expect(keepsKey(new TypeError('Failed to fetch'))).toBe(true);
	});

	it('keeps it on a server error: the reply may exist under that key', () => {
		expect(keepsKey(new ApiError(500, 'boom'))).toBe(true);
		expect(keepsKey(new ApiError(504, 'Gateway Timeout'))).toBe(true);
	});

	it('makes a new one after a refusal: nothing was saved under the key', () => {
		expect(keepsKey(new ApiError(409, '{"detail":"already_sending"}'))).toBe(false);
		expect(keepsKey(new ApiError(404, 'Not found'))).toBe(false);
	});
});

describe('failedCopy', () => {
	const refusal = (detail: string) => new ApiError(409, JSON.stringify({ detail }));

	it('says the draft is safe to send again when no answer came back', () => {
		expect(failedCopy(new TypeError('Failed to fetch'))).toBe(REPLY_COPY.no_answer);
		expect(failedCopy(new ApiError(502, 'Bad Gateway'))).toBe(REPLY_COPY.no_answer);
	});

	it('names the reason the server refused', () => {
		expect(failedCopy(refusal('already_sending'))).toBe(REPLY_COPY.already_sending);
		expect(failedCopy(refusal('no_mailbox'))).toBe(REPLY_COPY.no_mailbox);
		expect(failedCopy(refusal('send_not_allowed'))).toBe(REPLY_COPY.reconnect);
		expect(failedCopy(refusal('no_recipient'))).toBe(REPLY_COPY.no_recipient);
		expect(failedCopy(refusal('mailbox_inactive'))).toBe(REPLY_COPY.refused);
	});
});

describe('spendsKey', () => {
	it('spends the key once the reply has settled', () => {
		for (const status of ['sent', 'not_sent', 'unknown'] as const) {
			expect(spendsKey(reply({ status }))).toBe(true);
		}
	});

	it('keeps it while the reply is still sending: a press must get that row back', () => {
		expect(spendsKey(reply({ status: 'sending', sent_at: null }))).toBe(false);
	});
});
