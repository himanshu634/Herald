<script lang="ts">
	import type { EmailStatus } from '#lib/api/client.js';
	import {
		AngerMeter,
		Button,
		Dialog,
		FilterChip,
		Icon,
		Logo,
		HoverCard,
		Panel,
		StatusTag,
		Tabs,
		Tag,
		ThemeSwitch,
		Toast,
		URGENCY,
		type TabItem,
		type Urgency
	} from '#lib/ui/index.js';

	// The gallery for docs/design-system.md: every token and component, in both themes.
	const swatches = [
		['bg-canvas', 'Canvas, the page'],
		['bg-surface', 'Surface, panels'],
		['bg-sunken', 'Sunken: rail, table heads'],
		['bg-ink', 'Ink, text'],
		['bg-muted', 'Muted text'],
		['bg-line', 'Line'],
		['bg-accent', 'Accent, act here'],
		['bg-accent-base', 'Accent base']
	] as const;

	const type = [
		['text-4xl font-extrabold tracking-display', 'Display 42', '62 sorted today'],
		['text-3xl font-extrabold tracking-display', 'Hero 30', '3 need you now'],
		['text-2xl font-extrabold', 'Page title 24', 'Inbox'],
		['text-xl font-extrabold', 'Panel title 18', 'Refund still not received'],
		['text-lg font-bold', 'Row title 16', 'Flight on Thursday, still no bag'],
		['text-md', 'Body 14', 'Herald read every email and sorted it for you.'],
		['text-sm', 'Table 13', 'Refund of ₹6,499, 09:47'],
		['font-mono text-sm', 'Mono 13', 'TF-20418, riya@customer.in'],
		['text-xs font-semibold', 'Tag 12', 'Needs a look']
	] as const;

	const statuses: EmailStatus[] = [
		'alerted',
		'needs_a_look',
		'inbox',
		'in_progress',
		'done',
		'closed',
		'new'
	];
	const urgencies = Object.keys(URGENCY) as Urgency[];

	const tabs: TabItem[] = [
		{ id: 'needs-you', label: 'Needs you', count: 3, countTone: 'danger' },
		{ id: 'all', label: 'All mail', count: 62 },
		{ id: 'thread', label: 'Arjun Mehta' },
		{ id: 'rule-test', label: 'Rule test: Damaged bag' }
	];
	let tab = $state('needs-you');
	let anger4 = $state(true);
	let dialogOpen = $state(false);
	let toast = $state<string | null>(null);
	const th = 'h-8.5 border-b border-line bg-sunken px-3 text-left text-xs font-bold text-muted';
	const td = 'h-row border-b border-dashed border-line-dashed px-3 whitespace-nowrap';
</script>

<svelte:head><title>Design system · Herald</title></svelte:head>

<main class="mx-auto flex max-w-7xl flex-col gap-6 px-6 pt-8 pb-12">
	<header class="flex flex-wrap items-end justify-between gap-4">
		<div>
			<h1 class="text-4xl font-extrabold tracking-display">Herald design system</h1>
			<p class="text-muted">
				Direction M, Control room. Rules in <code class="font-mono">docs/design-system.md</code>.
			</p>
		</div>
		<ThemeSwitch labelled />
	</header>

	<div class="grid grid-cols-[repeat(auto-fit,minmax(min(100%,32rem),1fr))] items-start gap-4">
		<Panel title="Logo">
			<div class="flex flex-col gap-5">
				<div class="flex flex-wrap items-end gap-5">
					{#each [16, 24, 34, 56, 128] as size (size)}
						<div class="flex flex-col items-center gap-2">
							<Logo {size} />
							<span class="text-xs text-muted">{size} px</span>
						</div>
					{/each}
				</div>
				<div class="flex items-center gap-2.5">
					<Logo size={40} />
					<span class="text-3xl font-extrabold tracking-display">Herald</span>
				</div>
			</div>
		</Panel>

		<Panel title="Colour">
			<div class="grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-3 text-xs">
				{#each swatches as [utility, name] (utility)}
					<div class="flex flex-col gap-2">
						<span class={['h-11 rounded-sm border border-line', utility]}></span>
						<span><b>{name}</b><br /><code class="font-mono">{utility}</code></span>
					</div>
				{/each}
			</div>
		</Panel>

		<Panel title="Type, Schibsted Grotesk">
			<div class="flex flex-col gap-3">
				{#each type as [classes, name, sample] (name)}
					<div class="grid grid-cols-[7rem_1fr] items-baseline gap-3">
						<span class="text-sm text-muted">{name}</span>
						<span class={['wrap-anywhere', classes]}>{sample}</span>
					</div>
				{/each}
			</div>
		</Panel>

		<Panel title="Buttons press down">
			<div class="flex flex-col gap-3">
				<div class="flex flex-wrap items-center gap-2">
					<Button variant="primary" kbd="O">On it</Button>
					<Button kbd="N">Not urgent</Button>
					<Button kbd="D">Done</Button>
					<Button variant="quiet">Open thread</Button>
				</div>
				<div class="flex flex-wrap items-center gap-2">
					<Button variant="primary" size="sm">Save rule</Button>
					<Button size="sm">Test on past emails</Button>
					<Button size="sm" disabled>Disabled</Button>
				</div>
			</div>
		</Panel>

		<Panel title="Status, urgency and the safety floor">
			<div class="flex flex-col gap-3">
				<div class="flex flex-wrap gap-2">
					{#each statuses as status (status)}<StatusTag {status} />{/each}
				</div>
				<div class="flex flex-wrap gap-2">
					{#each urgencies as urgency (urgency)}
						<Tag tone={URGENCY[urgency].tone}>{URGENCY[urgency].label}</Tag>
					{/each}
				</div>
				<div class="flex flex-wrap gap-2">
					<Tag tone="floor" icon="shield">Safety floor: legal threat</Tag>
					<Tag tone="accent">Important contact</Tag>
					<Tag tone="neutral">About to cancel</Tag>
				</div>
			</div>
		</Panel>

		<Panel title="Anger, kept apart from urgency">
			<div class="flex flex-col gap-3">
				{#each [1, 2, 3, 4, 5] as level (level)}
					<AngerMeter {level} showLabel />
				{/each}
			</div>
		</Panel>

		<Panel title="Tabs and filters">
			<div class="flex flex-col gap-3">
				<Tabs items={tabs} bind:selected={tab} label="Inbox views" />
				<div class="flex flex-wrap gap-2">
					<FilterChip pressed>Status: needs you</FilterChip>
					<FilterChip>Topic</FilterChip>
					<FilterChip>Urgency</FilterChip>
					<FilterChip bind:pressed={anger4}>Anger 4+</FilterChip>
				</div>
			</div>
		</Panel>

		<Panel title="A table row">
			{#snippet actions()}<span class="text-sm text-muted">42px rows, dashed rules</span>{/snippet}
			<div class="overflow-x-auto">
				<table class="w-full min-w-136 border-collapse text-sm">
					<thead>
						<tr>
							<th class={th}>Status</th>
							<th class={th}>From</th>
							<th class={th}>Summary</th>
							<th class={th}>Urgency</th>
							<th class={th}>Anger</th>
						</tr>
					</thead>
					<tbody>
						<tr class="bg-accent-soft">
							<td class={[td, 'shadow-[inset_3px_0_0_var(--color-accent)]']}>
								<StatusTag status="alerted" />
							</td>
							<td class={[td, 'font-bold']}>Arjun Mehta</td>
							<td class={td}>Will file in consumer court if the refund isn't done by Friday</td>
							<td class={td}><Tag tone="danger">Urgent</Tag></td>
							<td class={td}><AngerMeter level={4} /></td>
						</tr>
						<tr>
							<td class={td}><StatusTag status="inbox" /></td>
							<td class={[td, 'font-bold']}>Neha Kapoor</td>
							<td class={td}>Wheel snapped on the first trip</td>
							<td class={td}><Tag tone="warning">High</Tag></td>
							<td class={td}><AngerMeter level={3} /></td>
						</tr>
					</tbody>
				</table>
			</div>
		</Panel>

		<Panel title="Toast">
			<div class="flex flex-wrap items-center gap-3">
				<Button onclick={() => (toast = 'Moved to Inbox. Herald saved this as a correction.')}
					>Show a toast</Button
				>
				<span class="text-sm text-muted">Bottom centre, the action's own words.</span>
			</div>
		</Panel>

		<Panel title="Dialog">
			<div class="flex flex-wrap items-center gap-3">
				<Button onclick={() => (dialogOpen = true)}>Open a dialog</Button>
				<span class="text-sm text-muted"
					>80% of the window, full screen on a phone. Esc closes it.</span
				>
			</div>
			<Dialog open={dialogOpen} label="Example dialog" onclose={() => (dialogOpen = false)}>
				{#snippet header()}
					<h2 class="text-xl font-extrabold">Do you take back pairs bought from a stockist?</h2>
				{/snippet}
				<div class="flex-1 px-5 py-4 text-md text-body">
					The body is laid out in columns from md up, and scrolls inside the dialog.
				</div>
				{#snippet footer()}
					<Button variant="primary" onclick={() => (dialogOpen = false)}>Save</Button>
					<Button variant="quiet" onclick={() => (dialogOpen = false)}>Not now</Button>
				{/snippet}
			</Dialog>
		</Panel>

		<Panel title="Theme switch">
			<div class="flex flex-wrap items-start gap-4">
				<ThemeSwitch labelled />
				<ThemeSwitch />
				<ThemeSwitch vertical />
				<span class="text-sm text-muted"
					>Saved in this browser. Labelled here, icons in the open rail, stacked in the closed one.</span
				>
			</div>
		</Panel>

		<Panel title="Hover card on a panel title">
			{#snippet info()}
				<p class="font-bold text-ink">What this panel is for, in one sentence.</p>
				<p class="mt-1">Then what it needs: required or optional, and its limits.</p>
			{/snippet}
			<p class="text-sm text-muted">
				Hover, focus or tap the title. Escape closes it. Inline, the same card reads
				<HoverCard label="like this">Short help that would clutter the screen.</HoverCard>.
			</p>
		</Panel>

		<Panel title="The safety floor callout">
			<div class="flex items-start gap-3 rounded-lg bg-floor-bg px-4 py-3 text-floor-fg">
				<Icon name="shield" size={18} />
				<p class="text-sm">
					Safety floor: legal threat. This always alerts you, whatever your rules say.
				</p>
			</div>
		</Panel>
	</div>
</main>

<Toast message={toast} ondismiss={() => (toast = null)} />
