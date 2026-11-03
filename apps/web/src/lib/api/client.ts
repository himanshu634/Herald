// Thin typed wrappers over the FastAPI routes. Types come from schema.d.ts (make gen-api).
import type { components } from './schema';

export type Workspace = components['schemas']['WorkspaceOut'];
export type Email = components['schemas']['EmailOut'];
export type EmailIn = components['schemas']['EmailIn'];
export type EmailStatus = components['schemas']['EmailStatus'];

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
	listEmails: (workspaceId: string) => request<Email[]>(`/workspaces/${workspaceId}/emails`),
	sendTestEmail: (workspaceId: string, email: EmailIn) =>
		request<Email>(`/workspaces/${workspaceId}/emails`, {
			method: 'POST',
			body: JSON.stringify(email)
		}),
	act: (workspaceId: string, emailId: string, action: 'on-it' | 'not-urgent' | 'done') =>
		request<Email>(`/workspaces/${workspaceId}/emails/${emailId}/${action}`, { method: 'POST' })
};
