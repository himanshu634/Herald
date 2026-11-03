<script lang="ts">
	import type { Email } from '#lib/api/client.js';
	import { Button, StatusTag } from '#lib/ui/index.js';
	import { formatTime, senderName } from './inbox';

	let { questions, onanswer }: { questions: Email[]; onanswer: (id: string) => void } = $props();
</script>

<section
	aria-labelledby="questions-title"
	class="overflow-hidden rounded-lg border-[1.5px] border-ink bg-surface"
>
	<header
		class="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 bg-warning-bg px-4 py-2 text-sm text-warning-fg"
	>
		<p id="questions-title">
			<b>
				{questions.length === 1
					? 'Herald has 1 question.'
					: `Herald has ${questions.length} questions.`}
			</b>
			{questions.length === 1 ? 'It stays' : 'They stay'} here, whatever tab or filter you pick, until
			you answer.
		</p>
		<p>Answering teaches Herald for next time</p>
	</header>
	<ul>
		{#each questions as email (email.id)}
			<li
				class="grid grid-cols-[auto_1fr_auto] items-center gap-3 border-t border-dashed border-line-dashed px-4 py-3 first:border-t-0"
			>
				<span
					aria-hidden="true"
					class="flex size-7 items-center justify-center rounded-md bg-accent text-lg font-extrabold text-on-accent"
					>?</span
				>
				<div class="min-w-0">
					<p class="text-lg leading-snug font-bold">
						{email.notes?.question ?? 'Herald isn’t sure how you’d want this one handled.'}
					</p>
					<p class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
						<span class="truncate">
							{senderName(email.sender)}: “{email.notes?.summary ?? email.subject}”
						</span>
						<StatusTag status={email.status} />
						<span>{formatTime(email.received_at)}</span>
					</p>
				</div>
				<Button size="sm" onclick={() => onanswer(email.id)}>Answer</Button>
			</li>
		{/each}
	</ul>
</section>
