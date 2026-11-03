// Thin typed wrappers over the FastAPI routes. Types come from schema.d.ts (make gen-api).
import type { components } from './schema';

export type Workspace = components['schemas']['WorkspaceOut'];
export type Email = components['schemas']['EmailOut'];
export type EmailIn = components['schemas']['EmailIn'];
export type EmailStatus = components['schemas']['EmailStatus'];
export type WorkspaceConfig = components['schemas']['WorkspaceConfig'];
export type Rule = components['schemas']['Rule'];
export type RuleAction = components['schemas']['RuleAction'];
export type SetupOut = components['schemas']['SetupOut'];
export type DraftOut = components['schemas']['DraftOut'];

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
	sendTestEmail: (workspaceId: string, email: EmailIn) =>
		request<Email>(`/workspaces/${workspaceId}/emails`, {
			method: 'POST',
			body: JSON.stringify(email)
		}),
	act: (workspaceId: string, emailId: string, action: 'on-it' | 'not-urgent' | 'done') =>
		request<Email>(`/workspaces/${workspaceId}/emails/${emailId}/${action}`, { method: 'POST' })
};
