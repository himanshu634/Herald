// Thin typed wrappers over the FastAPI routes. Types come from schema.d.ts (make gen-api).
import type { components } from './schema';

export type Workspace = components['schemas']['WorkspaceOut'];
export type Email = components['schemas']['EmailOut'];
export type EmailStatus = components['schemas']['EmailStatus'];
export type WorkspaceConfig = components['schemas']['WorkspaceConfig'];
export type Topic = components['schemas']['Topic'];
export type Rule = components['schemas']['Rule'];
export type RuleAction = components['schemas']['RuleAction'];
export type SetupOut = components['schemas']['SetupOut'];
export type DraftOut = components['schemas']['DraftOut'];
export type Mailbox = components['schemas']['MailboxOut'];
export type MailboxStatus = components['schemas']['MailboxStatus'];
export type ConnectOut = components['schemas']['ConnectOut'];
export type TryOut = components['schemas']['TryOut'];
export type Reply = components['schemas']['ReplyOut'];
export type ReplyIn = components['schemas']['ReplyIn'];

/** The server answered with an error status. The message stays "{status} {body}". */
export class ApiError extends Error {
	readonly status: number;
	readonly body: string;

	constructor(status: number, body: string) {
		super(`${status} ${body}`);
		this.name = 'ApiError';
		this.status = status;
		this.body = body;
	}

	/** FastAPI's `detail` when it is a string, like "already_sending". */
	get detail(): string | null {
		try {
			const detail = JSON.parse(this.body)?.detail;
			return typeof detail === 'string' ? detail : null;
		} catch {
			return null;
		}
	}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(`/api${path}`, {
		...init,
		headers: { 'Content-Type': 'application/json', ...init?.headers }
	});
	if (!response.ok) throw new ApiError(response.status, await response.text());
	return response.json() as Promise<T>;
}

export const api = {
	listWorkspaces: () => request<Workspace[]>('/workspaces'),
	createDemoWorkspace: () => request<Workspace>('/workspaces/demo', { method: 'POST' }),
	getWorkspace: (workspaceId: string) => request<Workspace>(`/workspaces/${workspaceId}`),
	/** Onboarding step one: a draft workspace holding the AI's first guess at its setup. */
	startSetup: (name: string, description: string) =>
		request<SetupOut>('/workspaces/setup', {
			method: 'POST',
			body: JSON.stringify({ name, description })
		}),
	/** Draft again from a description. Saves nothing. */
	suggestSetup: (workspaceId: string, description: string) =>
		request<DraftOut>(`/workspaces/${workspaceId}/setup/suggest`, {
			method: 'POST',
			body: JSON.stringify({ description })
		}),
	/** Save the owner's setup. Ends the draft, so the workspace starts taking email. */
	saveConfig: (workspaceId: string, name: string, config: WorkspaceConfig) =>
		request<Workspace>(`/workspaces/${workspaceId}/config`, {
			method: 'PUT',
			body: JSON.stringify({ name, config })
		}),
	listEmails: (workspaceId: string) => request<Email[]>(`/workspaces/${workspaceId}/emails`),
	act: (
		workspaceId: string,
		emailId: string,
		action: 'on-it' | 'not-urgent' | 'to-inbox' | 'done'
	) => request<Email>(`/workspaces/${workspaceId}/emails/${emailId}/${action}`, { method: 'POST' }),
	/** Triage the email again with the current facts and rules. The result arrives as email.noted. */
	reread: (workspaceId: string, emailId: string) =>
		request<Email>(`/workspaces/${workspaceId}/emails/${emailId}/reread`, { method: 'POST' }),
	/** What Herald would do with the email under an unsaved config. Saves nothing. */
	tryConfig: (workspaceId: string, emailId: string, config: WorkspaceConfig) =>
		request<TryOut>(`/workspaces/${workspaceId}/emails/${emailId}/try`, {
			method: 'POST',
			body: JSON.stringify({ config })
		}),
	/** Mail providers this server can connect, like ['gmail']. Empty when none is set up. */
	listProviders: () => request<string[]>('/providers'),
	listMailboxes: (workspaceId: string) =>
		request<Mailbox[]>(`/workspaces/${workspaceId}/mailboxes`),
	/** Start a connect. Send the browser to the returned URL; the provider sends it back to /. */
	/** Leave `readSpam` out on a reconnect: the mailbox keeps the owner's earlier choice. */
	startConnect: (workspaceId: string, provider: string, readSpam?: boolean) =>
		request<ConnectOut>(`/workspaces/${workspaceId}/mailboxes/${provider}/connect`, {
			method: 'POST',
			...(readSpam === undefined ? {} : { body: JSON.stringify({ read_spam: readSpam }) })
		}),
	/** Read the Spam folder too, or stop. Turning it on also reads the last 2 days of Spam. */
	setReadSpam: (workspaceId: string, mailboxId: string, readSpam: boolean) =>
		request<Mailbox>(`/workspaces/${workspaceId}/mailboxes/${mailboxId}`, {
			method: 'PATCH',
			body: JSON.stringify({ read_spam: readSpam })
		}),
	mailboxAction: (workspaceId: string, mailboxId: string, action: 'sync' | 'pause' | 'resume') =>
		request<Mailbox>(`/workspaces/${workspaceId}/mailboxes/${mailboxId}/${action}`, {
			method: 'POST'
		}),
	disconnectMailbox: (workspaceId: string, mailboxId: string) =>
		request<Mailbox>(`/workspaces/${workspaceId}/mailboxes/${mailboxId}`, { method: 'DELETE' }),
	/**
	 * Send the owner's reply. Answers 200 whatever the outcome: read the reply's `status`.
	 * A 409 means nothing was sent; its detail says why.
	 */
	reply: (workspaceId: string, emailId: string, data: ReplyIn) =>
		request<Reply>(`/workspaces/${workspaceId}/emails/${emailId}/replies`, {
			method: 'POST',
			body: JSON.stringify(data)
		}),
	/** The email's replies, oldest first. */
	replies: (workspaceId: string, emailId: string) =>
		request<Reply[]>(`/workspaces/${workspaceId}/emails/${emailId}/replies`)
};
