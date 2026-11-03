// Live workspace events over SSE. EventSource reconnects on its own and sends Last-Event-ID,
// so the server replays anything missed while the tab was disconnected.

export const EVENT_TYPES = [
	'email.received',
	'email.noted',
	'email.status',
	'alert.sent',
	'mailbox.status',
	'reply.status'
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

export interface WorkspaceEvent {
	id: string;
	type: EventType;
	data: Record<string, unknown>;
}

export class WorkspaceEvents {
	events = $state<WorkspaceEvent[]>([]);
	connected = $state(false);

	#source: EventSource | null = null;
	// Plain Set on purpose: listeners are never rendered, so they need no reactivity.
	// eslint-disable-next-line svelte/prefer-svelte-reactivity
	#listeners = new Set<(event: WorkspaceEvent) => void>();

	connect(workspaceId: string) {
		this.close();
		const source = new EventSource(`/api/workspaces/${workspaceId}/events`);
		source.onopen = () => (this.connected = true);
		source.onerror = () => (this.connected = false);
		for (const type of EVENT_TYPES) {
			source.addEventListener(type, (message) => {
				const event: WorkspaceEvent = {
					id: message.lastEventId,
					type,
					data: JSON.parse(message.data)
				};
				this.events = [event, ...this.events].slice(0, 50);
				for (const listener of this.#listeners) listener(event);
			});
		}
		this.#source = source;
	}

	onEvent(listener: (event: WorkspaceEvent) => void) {
		this.#listeners.add(listener);
		return () => this.#listeners.delete(listener);
	}

	close() {
		this.#source?.close();
		this.#source = null;
		this.connected = false;
	}
}
