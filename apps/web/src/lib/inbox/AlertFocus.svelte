<script lang="ts">
	import type { Email, Reply, WorkspaceConfig } from '#lib/api/client.js';
	import { AngerMeter, Button, Icon, Tag, URGENCY } from '#lib/ui/index.js';
	import {
		ACTIONS,
		actionsFor,
		alertRuleSentence,
		firedAlertRules,
		floorLabel,
		formatTime,
		highlight,
		senderName,
		tidyBody,
		type Action
	} from './inbox';
	import ReplyLine from './ReplyLine.svelte';
	import { REPLY_COPY, STATE_LOOK, STATUS_LOOK, replyNotice, type ReplyState } from './reply';

	let {
		email,
		position,
		total,
		config,
		busy,
		full,
		ontogglefull,
		onact,
		onmove,
		onanswer,
		replyState,
		replies,
		connecting,
		onreply,
		onreconnect
	}: {
		email: Email;
		/** Its place in the queue, from 1; null once it has left the queue (say, replied and done). */
		position: number | null;
		total: number;
		config: WorkspaceConfig;
		busy: boolean;
		/** The owner asked to read the whole email (the E key or the button). */
		full: boolean;
		ontogglefull: () => void;
		onact: (action: Action) => void;
		/** Step through the queue: the J and K keys, and buttons on narrow screens. */
		onmove: (step: number) => void;
		/** Open Herald's question about this alert. */
		onanswer: () => void;
		replyState: ReplyState;
		replies: Reply[];
		connecting: boolean;
		onreply: () => void;
		onreconnect: () => void;
	} = $props();

	const floor = $derived(floorLabel(email.decision?.floor_flags ?? []));
	const rules = $derived(firedAlertRules(email, config));
	const urgency = $derived(email.decision?.urgency ?? email.notes?.urgency);
	const quotes = $derived(email.notes?.quotes?.map((q) => tidyBody(q.text)).filter(Boolean) ?? []);
	const parts = $derived(highlight(tidyBody(email.body), quotes));
	const showFull = $derived(full || !email.notes);
	const actions = $derived(actionsFor(email.status));
	const name = $derived(senderName(email.sender));
</script>

<article aria-labelledby="alert-title" class="flex min-h-full flex-col bg-surface">
	<div class="flex max-w-200 flex-1 flex-col gap-5 px-5 py-5 lg:px-8 lg:py-6">
		<div class="flex flex-wrap items-center gap-2.5">
			{#if position}
				<Tag tone="danger">Alert {position} of {total}</Tag>
			{:else}
				<Tag tone="muted">Not an alert any more</Tag>
			{/if}
			{#if urgency}<Tag tone={URGENCY[urgency].tone}>{URGENCY[urgency].label}</Tag>{/if}
			{#if email.notes}<AngerMeter level={email.notes.anger} showLabel />{/if}
			<span class="flex-1"></span>
			<span class="text-sm text-muted">
				{formatTime(email.received_at)}{#if email.notes?.topic}, {email.notes.topic}{/if}
			</span>
			{#if total > 1 && position}
				<!-- The list sits below the alert on narrow screens; these save the scroll. -->
				<span class="flex gap-1 lg:hidden">
					<Button variant="quiet" size="sm" kbd="K" onclick={() => onmove(-1)}>Previous</Button>
					<Button variant="quiet" size="sm" kbd="J" onclick={() => onmove(1)}>Next</Button>
				</span>
			{/if}
		</div>

		<div>
			<p class="text-sm text-muted">
				<b class="text-ink">{name}</b>
				<span class="font-mono text-xs">{email.sender}</span>, “{email.subject}”
			</p>
			<h2 id="alert-title" class="mt-2 text-xl leading-snug font-bold tracking-title">
				{email.notes?.summary || email.subject}
			</h2>
			{#if email.in_spam}
				<p class="mt-2 flex items-start gap-2 text-sm text-neutral-fg">
					<Icon name="shield" size={16} />Gmail filed this in Spam. It stays there in Gmail.
				</p>
			{/if}
		</div>

		{#if quotes.length}
			<section aria-labelledby="words-title" class="flex flex-col gap-2">
				<h3 id="words-title" class="text-sm font-bold text-muted">In {name}’s words</h3>
				<ul class="flex flex-col gap-2">
					{#each quotes as quote, i (i)}
						<li
							class="self-start rounded-xs bg-accent-tint px-3 py-2 text-md text-ink shadow-[inset_0_-2px_0_var(--color-accent-base)]"
						>
							“{quote}”
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		<section aria-labelledby="alerted-title" class="flex flex-col gap-2">
			<h3 id="alerted-title" class="text-sm font-bold text-muted">Why Herald alerted you</h3>
			{#if floor}
				<div class="flex items-start gap-3 rounded-lg bg-floor-bg px-4 py-3 text-floor-fg">
					<Icon name="shield" size={18} />
					<p class="text-sm">{floor}. This always alerts you, whatever your rules say.</p>
				</div>
			{:else}
				<div class="rounded-lg border border-line bg-sunken px-4 py-3 text-md">
					<p class="font-bold">{email.decision?.reason ?? 'Herald is reading this email.'}</p>
					{#each rules as rule (rule.id)}
						<p class="mt-1 text-body">{alertRuleSentence(rule.when)}</p>
					{/each}
				</div>
			{/if}
		</section>

		{#if email.notes?.sure === false}
			<!-- An unsure alert stays an alert; its question rides along here, not in the list. -->
			<section
				aria-label="Herald's question"
				class="flex items-center gap-3 rounded-lg border-[1.5px] border-ink bg-warning-bg px-4 py-3 text-warning-fg"
			>
				<span
					aria-hidden="true"
					class="flex size-7 flex-none items-center justify-center rounded-md bg-accent text-lg font-extrabold text-on-accent"
					>?</span
				>
				<p class="flex-1 text-md font-bold">
					{email.notes.question ?? 'Herald isn’t sure how you’d want this one handled.'}
				</p>
				<Button size="sm" onclick={onanswer}>Answer</Button>
			</section>
		{/if}

		<section
			aria-labelledby="alert-email-title"
			class="border-t border-dashed border-line-dashed pt-4"
		>
			<div class="mb-2 flex items-center justify-between gap-3">
				<h3 id="alert-email-title" class="text-sm font-bold text-muted">The email</h3>
				{#if email.notes}
					<Button
						variant="quiet"
						size="sm"
						kbd="E"
						aria-expanded={showFull}
						aria-controls="alert-email-body"
						onclick={ontogglefull}>{showFull ? 'Hide' : 'Read it all'}</Button
					>
				{/if}
			</div>
			{#if showFull}
				<p id="alert-email-body" class="text-md whitespace-pre-line text-body">
					{#each parts as part, i (i)}{#if part.quoted}<mark
								class="rounded-[2px] bg-accent-tint px-0.5 text-ink shadow-[inset_0_-2px_0_var(--color-accent-base)]"
								>{part.text}</mark
							>{:else}{part.text}{/if}{/each}
				</p>
			{:else}
				<button
					id="alert-email-body"
					type="button"
					class="line-clamp-3 w-full cursor-pointer text-left text-sm text-muted hover:text-body"
					onclick={ontogglefull}>{tidyBody(email.body).replace(/\s*\n\s*/g, ' ')}</button
				>
			{/if}
		</section>

		{#if replies.length}
			<section
				aria-labelledby="alert-replies-title"
				class="flex flex-col gap-3 border-t border-dashed border-line-dashed pt-4"
			>
				<h3 id="alert-replies-title" class="text-sm font-bold text-muted">Your replies</h3>
				{#each replies as reply (reply.id)}
					<div class="flex flex-col gap-2">
						<ReplyLine look={STATUS_LOOK[reply.status]} text={replyNotice(reply)} />
						<p class="text-sm whitespace-pre-line text-body">{reply.body}</p>
					</div>
				{/each}
			</section>
		{/if}

		{#if replyState !== 'ok'}
			<ReplyLine look={STATE_LOOK[replyState]} text={REPLY_COPY[replyState]}>
				{#if replyState === 'reconnect'}
					<Button size="sm" disabled={connecting} onclick={onreconnect}>Reconnect Gmail</Button>
				{/if}
			</ReplyLine>
		{/if}
	</div>

	{#if actions.length || replyState === 'ok'}
		<!-- Pinned to the bottom so the actions stay under the thumb on a phone. -->
		<div
			class="sticky bottom-0 flex flex-wrap items-center justify-between gap-3 border-t border-line bg-surface px-5 py-3 lg:px-8"
		>
			<p class="text-sm text-muted max-sm:hidden">
				{#if position}When you act, the next alert opens. Not urgent saves a correction.{/if}
			</p>
			<div class="flex flex-wrap gap-2">
				{#each actions as action, i (action)}
					<Button
						variant={i === 0 ? 'primary' : 'secondary'}
						kbd={ACTIONS[action].key}
						disabled={busy}
						onclick={() => onact(action)}>{ACTIONS[action].label}</Button
					>
				{/each}
				{#if replyState === 'ok'}
					<Button variant={actions.length ? 'secondary' : 'primary'} kbd="R" onclick={onreply}
						>Reply</Button
					>
				{/if}
			</div>
		</div>
	{/if}
</article>
