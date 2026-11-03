<script lang="ts">
	import { prefs, type Theme } from '#lib/prefs.svelte.js';
	import Icon, { type IconName } from './Icon.svelte';

	// Three pressed-state buttons, not one that cycles, so the current choice is always visible.
	let {
		vertical = false,
		labelled = false
	}: {
		/** Stack the buttons, for the collapsed rail. */
		vertical?: boolean;
		/** Show the words next to the icons. */
		labelled?: boolean;
	} = $props();

	const OPTIONS: { id: Theme; label: string; icon: IconName }[] = [
		{ id: 'system', label: 'System', icon: 'monitor' },
		{ id: 'light', label: 'Light', icon: 'sun' },
		{ id: 'dark', label: 'Dark', icon: 'moon' }
	];
</script>

<div
	role="group"
	aria-label="Theme"
	class={[
		'inline-flex gap-0.5 rounded-md border border-line bg-subtle p-0.5',
		vertical && 'flex-col'
	]}
>
	{#each OPTIONS as option (option.id)}
		{@const on = prefs.theme === option.id}
		<button
			type="button"
			aria-pressed={on}
			aria-label={labelled ? undefined : `${option.label} theme`}
			title={labelled ? undefined : `${option.label} theme`}
			class={[
				'inline-flex h-control-sm cursor-pointer items-center justify-center gap-1.5 rounded-xs border text-sm font-semibold',
				labelled ? 'px-2.5' : 'w-control-sm',
				on ? 'border-line bg-surface text-ink' : 'border-transparent text-muted hover:text-ink'
			]}
			onclick={() => prefs.setTheme(option.id)}
		>
			<Icon name={option.icon} size={16} />
			{#if labelled}{option.label}{/if}
		</button>
	{/each}
</div>
