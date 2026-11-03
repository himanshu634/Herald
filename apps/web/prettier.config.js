/** @type {import("prettier").Config} */
const config = {
	useTabs: true,
	singleQuote: true,
	trailingComma: 'none',
	printWidth: 100,
	plugins: ['prettier-plugin-svelte', 'prettier-plugin-tailwindcss'],
	// Sorts Tailwind classes using Herald's theme (only its own tokens exist as utilities).
	tailwindStylesheet: './src/app.css',
	overrides: [{ files: '*.svelte', options: { parser: 'svelte' } }]
};

export default config;
