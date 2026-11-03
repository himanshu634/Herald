<script lang="ts">
	// The error page's scene: the logo's tile, with its lit row floated out of the pile and a
	// magnifying glass hunting for it. Shapes are the logo's (Logo.svelte) at 1.5x on this grid.
	// Decoration only: the page's heading says what went wrong.
	let { class: className }: { class?: string } = $props();
</script>

<svg viewBox="0 0 240 180" class={['overflow-visible', className]} aria-hidden="true">
	<!-- The floor, and the lit row's shadow on it. -->
	<line
		x1="16"
		y1="150"
		x2="224"
		y2="150"
		stroke-width="1.5"
		stroke-dasharray="4 6"
		stroke-linecap="round"
		class="stroke-line-strong"
	/>
	<ellipse
		cx="178"
		cy="152"
		rx="24"
		ry="4"
		class="origin-center animate-shadow fill-ink opacity-15 transform-fill"
	/>

	<!-- The tile, with an empty slot where the lit row belongs. -->
	<rect
		x="40.75"
		y="52.75"
		width="94.5"
		height="94.5"
		rx="21"
		stroke-width="1.5"
		class="fill-logo-tile stroke-logo-edge"
	/>
	<rect x="58" y="76" width="42" height="12" rx="6" class="fill-logo-row" />
	<rect
		x="70"
		y="94"
		width="48"
		height="12"
		rx="6"
		fill="none"
		stroke-width="1.5"
		stroke-dasharray="4 3"
		class="animate-march stroke-accent"
	/>
	<rect x="58" y="112" width="30" height="12" rx="6" class="fill-logo-row" />

	<!-- The magnifying glass. The surface-coloured halo keeps it readable over the dark tile. -->
	<g class="origin-center animate-search transform-fill">
		<g stroke-linecap="round" fill="none">
			<line x1="109" y1="109" x2="124" y2="124" stroke-width="10" class="stroke-surface" />
			<circle cx="96" cy="96" r="17" stroke-width="9" class="stroke-surface" />
			<line x1="109" y1="109" x2="124" y2="124" stroke-width="6" class="stroke-ink" />
			<circle cx="96" cy="96" r="17" stroke-width="4" class="fill-surface/25 stroke-ink" />
		</g>
	</g>

	<!-- The runaway: the lit row, drifting above the floor, wondering where it is. -->
	<g class="origin-center animate-drift transform-fill">
		<rect
			x="154"
			y="46"
			width="48"
			height="12"
			rx="6"
			stroke-width="1.5"
			class="fill-accent stroke-accent-edge"
		/>
	</g>
	<g class="fill-muted text-xl font-extrabold">
		<text x="206" y="36" class="animate-wonder">?</text>
		<text x="220" y="22" class="animate-wonder [animation-delay:0.4s]">?</text>
		<text x="190" y="20" class="animate-wonder [animation-delay:0.8s]">?</text>
	</g>
</svg>
