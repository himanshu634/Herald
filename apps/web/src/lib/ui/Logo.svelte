<script lang="ts">
	// The Herald mark: three emails, one pulled out of the pile and lit.
	// favicon.svg and apple-touch-icon.png draw the same shapes; change all three together.
	let { size = 32, label }: { size?: number; label?: string } = $props();
</script>

<!-- The rows sit on a 4-unit grid so they land on whole pixels at 16 and 32 px. -->
<svg
	width={size}
	height={size}
	viewBox="0 0 64 64"
	class="flex-none"
	role={label ? 'img' : undefined}
	aria-label={label}
	aria-hidden={label ? undefined : 'true'}
>
	<rect
		x="0.75"
		y="0.75"
		width="62.5"
		height="62.5"
		rx="14.25"
		stroke-width="1.5"
		class="fill-logo-tile stroke-logo-edge"
	/>
	<rect x="12" y="16" width="28" height="8" rx="4" class="fill-logo-row" />
	<rect x="20" y="28" width="32" height="8" rx="4" class="fill-accent" />
	<rect x="12" y="40" width="20" height="8" rx="4" class="fill-logo-row" />
</svg>
