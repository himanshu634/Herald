<script lang="ts">
	import type { EmailStatus } from '#lib/api/client.js';
	import {
		AngerMeter,
		Button,
		FilterChip,
		Icon,
		Panel,
		StatusTag,
		Tabs,
		Tag,
		URGENCY,
		type TabItem,
		type Urgency
	} from '#lib/ui/index.js';

	// The gallery for docs/design-system.md: every token and component, in both themes.
	const swatches = [
		['--color-bg', 'Concrete, the page'],
		['--color-surface', 'Panel'],
		['--color-surface-sunken', 'Sunken: rails, table heads'],
		['--color-text', 'Ink'],
		['--color-text-muted', 'Muted text'],
		['--color-border', 'Border'],
		['--color-accent', 'Chartreuse, act here'],
		['--color-accent-base', 'Press base']
	] as const;

	const type = [
		['--text-4xl', 'Display 42', '62 sorted today', 800],
		['--text-3xl', 'Hero 30', '3 need you now', 800],
		['--text-2xl', 'Page title 24', 'Inbox', 800],
		['--text-xl', 'Panel title 18', 'Refund still not received', 800],
		['--text-lg', 'Row title 16', 'Flight on Thursday, still no bag', 700],
		['--text-md', 'Body 14', 'Herald read every email and sorted it for you.', 400],
		['--text-sm', 'Table 13', 'Orders and delivery', 400],
		['--text-xs', 'Tag 12', 'Needs a look', 600]
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
	let theme = $state<'light' | 'dark' | null>(null);

	function setTheme(next: 'light' | 'dark') {
		theme = next;
		document.documentElement.dataset.theme = next;
	}
</script>

<svelte:head><title>Design system · Herald</title></svelte:head>

<main>
	<header class="top">
		<div>
			<h1>Herald design system</h1>
			<p class="muted">Direction M, Control room. Rules in <code>docs/design-system.md</code>.</p>
		</div>
		<div class="row">
			<Button
				variant={theme === 'light' ? 'primary' : 'secondary'}
				size="sm"
				onclick={() => setTheme('light')}>Light</Button
			>
			<Button
				variant={theme === 'dark' ? 'primary' : 'secondary'}
				size="sm"
				onclick={() => setTheme('dark')}>Dark</Button
			>
		</div>
	</header>

	<div class="grid">
		<Panel title="Colour">
			<div class="swatches">
				{#each swatches as [token, name] (token)}
					<div class="swatch">
						<span class="chip" style:background={`var(${token})`}></span>
						<span><b>{name}</b><br /><code>{token}</code></span>
					</div>
				{/each}
			</div>
		</Panel>

		<Panel title="Type, Albert Sans">
			<div class="stack">
				{#each type as [token, name, sample, weight] (token)}
					<div class="type-row">
						<span class="muted small">{name}</span>
						<span style:font-size={`var(${token})`} style:font-weight={weight} class="sample"
							>{sample}</span
						>
					</div>
				{/each}
			</div>
		</Panel>

		<Panel title="Buttons press down">
			<div class="stack">
				<div class="row">
					<Button variant="primary" kbd="O">On it</Button>
					<Button kbd="N">Not urgent</Button>
					<Button kbd="D">Done</Button>
					<Button variant="quiet">Open thread</Button>
				</div>
				<div class="row">
					<Button variant="primary" size="sm">Save rule</Button>
					<Button size="sm">Test on past emails</Button>
					<Button size="sm" disabled>Disabled</Button>
				</div>
			</div>
		</Panel>

		<Panel title="Status, urgency and the safety floor">
			<div class="stack">
				<div class="row">
					{#each statuses as status (status)}<StatusTag {status} />{/each}
				</div>
				<div class="row">
					{#each urgencies as urgency (urgency)}
						<Tag tone={URGENCY[urgency].tone}>{URGENCY[urgency].label}</Tag>
					{/each}
				</div>
				<div class="row">
					<Tag tone="floor" icon="shield">Safety floor: legal threat</Tag>
					<Tag tone="accent">Important contact</Tag>
					<Tag tone="neutral">About to cancel</Tag>
				</div>
			</div>
		</Panel>

		<Panel title="Anger, kept apart from urgency">
			<div class="stack">
				{#each [1, 2, 3, 4, 5] as level (level)}
					<AngerMeter {level} showLabel />
				{/each}
			</div>
		</Panel>

		<Panel title="Tabs and filters">
			<div class="stack">
				<Tabs items={tabs} bind:selected={tab} label="Inbox views" />
				<div class="row">
					<FilterChip pressed>Status: needs you</FilterChip>
					<FilterChip>Topic</FilterChip>
					<FilterChip>Urgency</FilterChip>
					<FilterChip bind:pressed={anger4}>Anger 4+</FilterChip>
				</div>
			</div>
		</Panel>

		<Panel title="A table row">
			{#snippet actions()}<span class="muted small">42px rows, dashed rules</span>{/snippet}
			<div class="table-wrap">
				<table>
					<thead>
						<tr><th>Status</th><th>From</th><th>Summary</th><th>Urgency</th><th>Anger</th></tr>
					</thead>
					<tbody>
						<tr class="selected">
							<td><StatusTag status="alerted" /></td>
							<td><b>Arjun Mehta</b></td>
							<td>Will file in consumer court if the refund isn't done by Friday</td>
							<td><Tag tone="danger">Urgent</Tag></td>
							<td><AngerMeter level={4} /></td>
						</tr>
						<tr>
							<td><StatusTag status="inbox" /></td>
							<td><b>Neha Kapoor</b></td>
							<td>Wheel snapped on the first trip</td>
							<td><Tag tone="warning">High</Tag></td>
							<td><AngerMeter level={3} /></td>
						</tr>
					</tbody>
				</table>
			</div>
		</Panel>

		<Panel title="The safety floor callout">
			<div class="floor">
				<Icon name="shield" size={18} />
				<p>Safety floor: legal threat. This always alerts you, whatever your rules say.</p>
			</div>
		</Panel>
	</div>
</main>

<style>
	main {
		max-width: 80rem;
		margin: 0 auto;
		padding: var(--space-8) var(--space-6) var(--space-12);
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.top {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: var(--space-4);
		flex-wrap: wrap;
	}

	h1 {
		font-size: var(--text-4xl);
		font-weight: var(--weight-heavy);
		letter-spacing: var(--tracking-display);
	}

	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 32rem), 1fr));
		gap: var(--space-4);
		align-items: start;
	}

	.stack {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2);
	}

	.muted {
		color: var(--color-text-muted);
	}

	.small {
		font-size: var(--text-sm);
	}

	.swatches {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr));
		gap: var(--space-3);
		font-size: var(--text-xs);
	}

	.swatch {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.chip {
		height: 2.75rem;
		border: var(--border-hair) solid var(--color-border);
		border-radius: var(--radius-sm);
	}

	.type-row {
		display: grid;
		grid-template-columns: 7rem 1fr;
		align-items: baseline;
		gap: var(--space-3);
	}

	.sample {
		line-height: var(--leading-tight);
		overflow-wrap: anywhere;
	}

	.table-wrap {
		overflow-x: auto;
	}

	table {
		min-width: 34rem;
		width: 100%;
		border-collapse: collapse;
		font-size: var(--text-sm);
	}

	th {
		height: 2.125rem;
		padding: 0 var(--space-3);
		background: var(--color-surface-sunken);
		color: var(--color-text-muted);
		font-size: var(--text-xs);
		font-weight: var(--weight-bold);
		text-align: left;
		border-bottom: var(--border-hair) solid var(--color-border);
	}

	td {
		white-space: nowrap;
		height: var(--row-height);
		padding: 0 var(--space-3);
		border-bottom: var(--border-hair) dashed var(--color-border-dashed);
	}

	tr.selected td {
		background: var(--color-accent-soft);
	}

	tr.selected td:first-child {
		box-shadow: inset 3px 0 0 var(--color-accent);
	}

	.floor {
		display: flex;
		gap: var(--space-3);
		align-items: flex-start;
		padding: var(--space-3) var(--space-4);
		border-radius: var(--radius-lg);
		background: var(--tone-floor-bg);
		color: var(--tone-floor-fg);
	}

	.floor p {
		color: var(--tone-floor-fg);
		font-size: var(--text-sm);
		line-height: var(--leading-normal);
	}
</style>
