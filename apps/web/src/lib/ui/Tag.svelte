<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon, { type IconName } from './Icon.svelte';
	import { TONE_CLASSES, type Tone } from './tones';

	let {
		tone = 'neutral',
		icon,
		children
	}: { tone?: Tone; icon?: IconName; children: Snippet } = $props();
</script>

<span
	class={[
		'inline-flex h-5 items-center gap-1 rounded-xs px-1.5 text-xs leading-none font-semibold whitespace-nowrap',
		TONE_CLASSES[tone]
	]}
>
	{#if icon}<Icon name={icon} size={11} />{/if}
	{@render children()}
</span>
