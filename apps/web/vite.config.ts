import { defineConfig } from 'vitest/config';
import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// A single-page app: FastAPI owns all server logic.
			adapter: adapter({ fallback: 'index.html' })
		})
	],
	server: {
		// Same origin for fetch and EventSource in dev, so no CORS and cookies just work.
		// HERALD_API_URL points the proxy at the api container under infra/docker-compose.dev.yml.
		proxy: { '/api': process.env.HERALD_API_URL ?? 'http://localhost:8000' }
	},
	test: {
		expect: { requireAssertions: true },
		projects: [
			{
				extends: './vite.config.ts',
				test: {
					name: 'server',
					environment: 'node',
					include: ['src/**/*.{test,spec}.{js,ts}'],
					exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
				}
			}
		]
	}
});
