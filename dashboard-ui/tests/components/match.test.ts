import { render, waitFor, within } from '@testing-library/svelte';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import MatchDetail from '../../src/surfaces/MatchDetail.svelte';

const dir = resolve(__dirname, '../fixtures/bundle');
const files = readdirSync(resolve(dir, 'fixtures'));
// A fixture whose edge is a coverage-gap (the common case), and one with a REAL edge node.
const gappedEdgeId = files[0].replace(/\.json$/, '');
const realEdgeId = files
  .find((f) => {
    const d = JSON.parse(readFileSync(resolve(dir, 'fixtures', f), 'utf8')).data;
    return d.edge && d.edge.coverage_gap !== true;
  })!
  .replace(/\.json$/, '');

beforeEach(() => {
  globalThis.fetch = (async (url: string) => {
    const rel = String(url).replace(/^.*\/bundle\//, '');
    return { ok: true, json: async () => JSON.parse(readFileSync(resolve(dir, rel), 'utf8')) } as Response;
  }) as typeof fetch;
});

test('Match detail renders the grid, win-bar, the why with CI, and a coverage gap', async () => {
  const { container } = render(MatchDetail, { baseUrl: '/bundle', matchId: gappedEdgeId });
  // the scoreline distribution carries its own uncertainty (ScorePill / WinBar / grid)
  await waitFor(() => expect(container.querySelector('[data-uncertainty="distribution"]')).toBeInTheDocument());
  // team strength shows a credible interval (data-estimate wrapping a data-uncertainty marker)
  await waitFor(() => expect(container.querySelector('[data-estimate] [data-uncertainty]')).toBeInTheDocument());
  // a coverage-gapped why field (xg) renders as a gap, never a number
  expect(container.querySelector('[data-coverage-gap]')).toBeInTheDocument();
});

test('Match detail routes the most-likely score + shortlist through ScorePill (no naked score)', async () => {
  const { container } = render(MatchDetail, { baseUrl: '/bundle', matchId: gappedEdgeId });
  await waitFor(() => expect(container.querySelector('[data-uncertainty="distribution"]')).toBeInTheDocument());
  // Every scoreline is a distribution readout: at least the headline + the whole shortlist.
  const pills = container.querySelectorAll('[data-uncertainty="distribution"]');
  expect(pills.length).toBeGreaterThanOrEqual(2);
  // No "±?" unknown-SE token must leak into a known scoreline distribution.
  expect(container.textContent).not.toContain('±?');
});

test('Match detail labels recent_form as raw results history, not a forecast', async () => {
  const { container, getByText } = render(MatchDetail, { baseUrl: '/bundle', matchId: gappedEdgeId });
  await waitFor(() => expect(container.querySelector('[data-uncertainty="distribution"]')).toBeInTheDocument());
  // It must read as data ("recent results" / "raw"), never as a model claim.
  expect(getByText(/recent (results|form)/i)).toBeInTheDocument();
});

test('Match detail renders a REAL edge through EdgeChip (not a naked number)', async () => {
  const { container } = render(MatchDetail, { baseUrl: '/bundle', matchId: realEdgeId });
  await waitFor(() => expect(container.querySelector('[data-uncertainty="distribution"]')).toBeInTheDocument());
  // The edge chip is present and carries the synthetic/NON-REAL provenance for synthetic odds.
  const edgeSection = container.querySelector('[data-section="edge"]') as HTMLElement;
  expect(edgeSection).toBeInTheDocument();
  // chip (▲/▼ + signed %) lives inside the edge section
  expect(within(edgeSection).getByText(/▲|▼|no edge/)).toBeInTheDocument();
});

// ── GHOST LINE (spec §4) ──────────────────────────────────────────────────────────
// When the fixture's edge carries the de-vigged ENTRY market_1x2, the MatchDetail WinBar
// ghosts that sharp line: the `.ghost` markers + the "line:" legend render inside the
// marked distribution region. The committed Brazil-Mexico detail carries the line.
test('Match detail ghosts the de-vigged market line into the WinBar when the edge carries market_1x2', async () => {
  const { container } = render(MatchDetail, { baseUrl: '/bundle', matchId: realEdgeId });
  await waitFor(() => expect(container.querySelector('[data-uncertainty="distribution"]')).toBeInTheDocument());
  // The ghosted sharp-line markers painted inside the win-bar.
  await waitFor(() => expect(container.querySelector('.ghost')).toBeTruthy());
  // The "line:" legend readout rendered and sits inside the marked distribution region.
  const legend = container.querySelector('.ln') as HTMLElement;
  expect(legend).toBeTruthy();
  expect(legend.textContent).toMatch(/line:\s*H/);
  expect(legend.closest('[data-uncertainty="distribution"]')).toBeTruthy();
});

test('Match detail renders NO ghost line when the edge is a coverage gap', async () => {
  const { container } = render(MatchDetail, { baseUrl: '/bundle', matchId: gappedEdgeId });
  await waitFor(() => expect(container.querySelector('[data-uncertainty="distribution"]')).toBeInTheDocument());
  // A gapped-edge fixture carries no market_1x2 -> the WinBar shows no ghosted line.
  expect(container.querySelector('.ghost')).toBeNull();
  expect(container.querySelector('.ln')).toBeNull();
});
