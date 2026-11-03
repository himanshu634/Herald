<script lang="ts">
	let { message, ondismiss }: { message: string | null; ondismiss: () => void } = $props();
</script>

<!-- Always in the DOM so screen readers hear each new message. -->
<div class="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center px-4">
	<div role="status" aria-live="polite">
		{#if message}
			<div
				class="pointer-events-auto flex items-center gap-3 rounded-lg bg-ink py-2 pr-2 pl-4 text-md text-canvas shadow-popover"
			>
				<p>{message}</p>
				<button
					type="button"
					class="h-control-sm cursor-pointer rounded-sm px-2 text-sm font-bold text-accent"
					onclick={ondismiss}>Dismiss</button
				>
			</div>
		{/if}
	</div>
</div>
