<script lang="ts">
	import '../app.css';
	import touchIcon from '#lib/assets/apple-touch-icon.png';
	import favicon from '#lib/assets/favicon.svg';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} type="image/svg+xml" />
	<link rel="apple-touch-icon" href={touchIcon} />
</svelte:head>

{@render children()}
