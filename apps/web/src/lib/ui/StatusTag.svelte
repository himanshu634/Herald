<script lang="ts">
	import type { EmailStatus } from '#lib/api/client.js';
	import Tag from './Tag.svelte';
	import { STATUS } from './tones';

	let { status }: { status: EmailStatus } = $props();

	const meta = $derived(STATUS[status]);
</script>

<Tag tone={meta.tone}>{meta.label}</Tag>
