// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		interface PageState {
			/** Set by setup after saving, so the inbox opens on that business. */
			workspace?: string;
		}
		// interface Platform {}
	}
}

export {};
