<script lang="ts">
	import '@fontsource-variable/albert-sans';
	import '#lib/styles/tokens.css';
	import '#lib/styles/base.css';
	import favicon from '#lib/assets/favicon.svg';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{@render children()}
