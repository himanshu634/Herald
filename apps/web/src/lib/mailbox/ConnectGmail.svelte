<script lang="ts">
	import { Button, Icon } from '#lib/ui/index.js';

	// The only thing a business without a mailbox shows: it stays closed until mail can flow.
	let {
		business,
		available,
		busy = false,
		onconnect
	}: {
		business: string;
		/** False when this server has no Gmail set up, so the button would only fail. */
		available: boolean;
		busy?: boolean;
		onconnect: () => void;
	} = $props();
</script>

<main class="flex flex-1 items-center justify-center p-6">
	<section
		aria-labelledby="connect-title"
		class="flex w-full max-w-215 flex-wrap gap-8 rounded-lg border-[1.5px] border-ink bg-surface p-7 shadow-[0_3px_0_var(--color-ink)]"
	>
		<div class="flex min-w-64 flex-1 flex-col gap-3">
			<h1 id="connect-title" class="text-2xl font-extrabold tracking-title">
				Connect the Gmail your customers write to
			</h1>
			<p class="text-muted">
				Herald opens {business} once its mail is connected. It reads new mail as it arrives, writes notes
				on each email and alerts you only when your rules say so.
			</p>
			{#if available}
				<Button variant="primary" class="mt-1.5 self-start" disabled={busy} onclick={onconnect}>
					<Icon name="mail" size={16} />{busy ? 'Opening Google…' : 'Connect Gmail'}
				</Button>
			{:else}
				<p class="mt-1.5 rounded-md bg-warning-bg px-3.5 py-2.5 text-sm text-warning-fg">
					Gmail isn’t set up on this Herald server yet. Add the Google settings to its
					<code>.env</code> and restart it.
				</p>
			{/if}
		</div>
		<ul class="flex w-full max-w-85 flex-col gap-2 text-sm">
			<li class="flex items-start gap-2">
				<span class="text-success-fg"><Icon name="check" size={16} /></span>
				Herald reads your mail to write notes and decide what alerts you.
			</li>
			<li class="flex items-start gap-2">
				<span class="text-danger-fg"><Icon name="close" size={16} /></span>
				It sends only replies you write and send yourself. It can’t delete or change your mail. Google
				grants read and send access, nothing more.
			</li>
			<li class="flex items-start gap-2">
				<span class="text-success-fg"><Icon name="check" size={16} /></span>
				You can pause or disconnect at any time.
			</li>
		</ul>
	</section>
</main>
