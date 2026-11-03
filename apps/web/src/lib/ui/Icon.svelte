<script lang="ts" module>
	// Line icons, 24px grid, 1.8 stroke. Add a glyph here rather than pasting SVG into a screen.
	const PATHS = {
		mail: '<path d="M3 7l9 6 9-6"/><rect x="3" y="5" width="18" height="14" rx="2"/>',
		inbox: '<path d="M3 13l3-8h12l3 8v6H3z"/><path d="M3 13h5l1 2h6l1-2h5"/>',
		rules: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
		business: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5h8v2"/>',
		chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
		shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
		bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 8 3 8H3s3-1 3-8"/><path d="M10 20a2 2 0 0 0 4 0"/>',
		search: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4-4"/>',
		close: '<path d="M6 6l12 12M18 6L6 18"/>',
		check: '<path d="M5 12l5 5 9-10"/>'
	} as const;

	export type IconName = keyof typeof PATHS;
</script>

<script lang="ts">
	let {
		name,
		size = 20,
		label
	}: {
		name: IconName;
		size?: number;
		/** Give a label only when the icon stands alone; next to text it is decoration. */
		label?: string;
	} = $props();
</script>

<svg
	width={size}
	height={size}
	class="block flex-none"
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="1.8"
	stroke-linecap="round"
	stroke-linejoin="round"
	role={label ? 'img' : undefined}
	aria-label={label}
	aria-hidden={label ? undefined : 'true'}
>
	<!-- eslint-disable-next-line svelte/no-at-html-tags -- static glyphs from PATHS above -->
	{@html PATHS[name]}
</svg>
