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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(`/api${path}`, {
		...init,
		headers: { 'Content-Type': 'application/json', ...init?.headers }
	});
	if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
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
	act: (workspaceId: string, emailId: string, action: 'on-it' | 'not-urgent' | 'done') =>
		request<Email>(`/workspaces/${workspaceId}/emails/${emailId}/${action}`, { method: 'POST' }),
	/** Mail providers this server can connect, like ['gmail']. Empty when none is set up. */
	listProviders: () => request<string[]>('/providers'),
	listMailboxes: (workspaceId: string) =>
		request<Mailbox[]>(`/workspaces/${workspaceId}/mailboxes`),
	/** Start a connect. Send the browser to the returned URL; the provider sends it back to /. */
	startConnect: (workspaceId: string, provider: string) =>
		request<ConnectOut>(`/workspaces/${workspaceId}/mailboxes/${provider}/connect`, {
			method: 'POST'
		}),
	mailboxAction: (workspaceId: string, mailboxId: string, action: 'sync' | 'pause' | 'resume') =>
		request<Mailbox>(`/workspaces/${workspaceId}/mailboxes/${mailboxId}/${action}`, {
			method: 'POST'
		}),
	disconnectMailbox: (workspaceId: string, mailboxId: string) =>
		request<Mailbox>(`/workspaces/${workspaceId}/mailboxes/${mailboxId}`, { method: 'DELETE' })
};
