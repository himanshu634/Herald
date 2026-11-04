<script lang="ts">
	import { Button, Icon } from '#lib/ui/index.js';
	import type { ViewId } from './inbox';

	let {
		address,
		questions,
		needsALook,
		onanswer,
		onview
	}: {
		/** The mailbox Herald reads, if one is connected. */
		address?: string;
		/** How many questions Herald has (they are listed beside this). */
		questions: number;
		needsALook: number;
		onanswer: () => void;
		onview: (view: ViewId) => void;
	} = $props();
</script>

<!-- The desk with nothing on it says what is next, so the owner is never left on a blank page. -->
<section
	aria-labelledby="clear-title"
	class="flex flex-1 items-center justify-center bg-surface px-5 py-12"
>
	<div class="flex w-full max-w-140 flex-col items-center gap-4 text-center">
		<span class="flex size-14 items-center justify-center rounded-xl bg-success-bg text-success-fg"
			><Icon name="check" size={28} /></span
		>
		<h2 id="clear-title" class="text-2xl font-extrabold tracking-title">No alerts</h2>
		<p class="text-md text-body">
			Herald keeps reading {address ?? 'your mail'} and puts an email here the moment it can’t wait.
		</p>
		{#if questions || needsALook}
			<div class="mt-2 flex w-full flex-col rounded-lg border border-line text-left">
				{#if questions}
					<div class="flex items-center gap-3 px-4 py-3">
						<p class="flex-1 text-md">
							<b
								>{questions === 1
									? 'Herald has 1 question'
									: `Herald has ${questions} questions`}</b
							>
							<span class="block text-sm text-muted">Answering teaches Herald for next time.</span>
						</p>
						<Button size="sm" onclick={onanswer}>Answer</Button>
					</div>
				{/if}
				{#if needsALook}
					<div
						class={[
							'flex items-center gap-3 px-4 py-3',
							questions && 'border-t border-dashed border-line-dashed'
						]}
					>
						<p class="flex-1 text-md">
							<b>{needsALook} {needsALook === 1 ? 'needs' : 'need'} a look</b>
							<span class="block text-sm text-muted"
								>Herald couldn’t read them. They never alert.</span
							>
						</p>
						<Button size="sm" onclick={() => onview('needs-a-look')}>Open Needs a look</Button>
					</div>
				{/if}
			</div>
		{/if}
		<button
			type="button"
			class="cursor-pointer text-sm font-bold text-ink underline underline-offset-2"
			onclick={() => onview('inbox')}>Go to the inbox</button
		>
	</div>
</section>
