import type {
  Envelope, Provenance, ScheduleData, TournamentData, TrackData, MetaData, FixtureDetail,
  StandingsData, ValueBundle, ValueBet, ValueCoverageGap,
} from './types';

export function unwrap<T>(e: Envelope<T>): T { return e.data; }
export function provenanceOf<T>(e: Envelope<T>): Provenance { return e.provenance; }

async function getJson<T>(url: string): Promise<Envelope<T>> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`failed to load ${url}: ${r.status}`);
  return (await r.json()) as Envelope<T>;
}

// Optional artifact: a PRE-FEATURE bundle (built before Item A) has no standings.json. We
// fetch it best-effort and return null on any failure (404 / parse error) so the standings
// chip degrades cleanly to a coverage gap rather than taking the whole Forecast group down.
async function getJsonOptional<T>(url: string): Promise<Envelope<T> | null> {
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    return (await r.json()) as Envelope<T>;
  } catch {
    return null;
  }
}

export interface Bundle {
  meta: Envelope<MetaData>;
  schedule: Envelope<ScheduleData>;
  tournament: Envelope<TournamentData>;
  track: Envelope<TrackData>;
  // OPTIONAL (Item A): null on a pre-feature bundle with no standings.json — the standings
  // chip then renders a coverage gap, never a crash.
  standings: Envelope<StandingsData> | null;
}

export async function loadBundle(baseUrl: string): Promise<Bundle> {
  const b = baseUrl.replace(/\/$/, '');
  const [meta, schedule, tournament, track, standings] = await Promise.all([
    getJson<MetaData>(`${b}/meta.json`),
    getJson<ScheduleData>(`${b}/schedule.json`),
    getJson<TournamentData>(`${b}/tournament.json`),
    getJson<TrackData>(`${b}/track.json`),
    getJsonOptional<StandingsData>(`${b}/standings.json`),
  ]);
  return { meta, schedule, tournament, track, standings };
}

export function loadFixture(baseUrl: string, matchId: string): Promise<Envelope<FixtureDetail>> {
  return getJson<FixtureDetail>(`${baseUrl.replace(/\/$/, '')}/fixtures/${matchId}.json`);
}

// ── Value bundle loader (the PRIMARY surface) ───────────────────────────────────
// The value bundle is wire-snake_case ({scan_ts, soft_book, ...}); we map snake→camel
// here so the surface reads typed camelCase props (same split-of-concern as the model
// loader). The NOT-REAL banner is ASSERTED present — a value bundle that ever lost its
// SIGNAL-ONLY / NON-REAL stamp must fail loud, never silently read as real/actionable.

interface RawValueBet {
  event: string; commence_time: string; market: string; line: number | null; side: string;
  sharp_book: string; sharp_fair_prob: number; soft_book: string; soft_odds: number;
  edge: number; suggested_stake: number; book_tier: string; last_update: string | null;
  flags: string[]; bettable: boolean;
}
interface RawValueGap { event: string; market: string; line: number | null; reason: string; }
interface RawValueBundle {
  provenance: {
    scan_ts: string; sharp_book: string; regions: string; credits_used: number;
    credits_remaining: number; git: string; schema_version: number;
    signal_only: boolean; is_synthetic: boolean; banner: string;
  };
  data: { bettable: RawValueBet[]; filtered: RawValueBet[]; coverage_gaps: RawValueGap[] };
}

function mapValueBet(b: RawValueBet): ValueBet {
  return {
    event: b.event, commenceTime: b.commence_time, market: b.market, line: b.line, side: b.side,
    sharpBook: b.sharp_book, sharpFairProb: b.sharp_fair_prob, softBook: b.soft_book,
    softOdds: b.soft_odds, edge: b.edge, suggestedStake: b.suggested_stake,
    bookTier: b.book_tier, lastUpdate: b.last_update, flags: b.flags ?? [], bettable: b.bettable,
  };
}
function mapValueGap(g: RawValueGap): ValueCoverageGap {
  return { event: g.event, market: g.market, line: g.line, reason: g.reason };
}

export async function loadValueBundle(url: string): Promise<ValueBundle> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`failed to load ${url}: ${r.status}`);
  const raw = (await r.json()) as RawValueBundle;
  const p = raw.provenance;
  // Fail-loud honesty: a value bundle with no NOT-REAL banner has lost its SIGNAL-ONLY
  // stamp; refuse to render it rather than let it read as actionable/real.
  if (!p || !p.banner) throw new Error('value bundle missing NOT-REAL banner (SIGNAL-ONLY stamp)');
  return {
    provenance: {
      scanTs: p.scan_ts, sharpBook: p.sharp_book, regions: p.regions, creditsUsed: p.credits_used,
      creditsRemaining: p.credits_remaining, git: p.git, schemaVersion: p.schema_version,
      signalOnly: p.signal_only, isSynthetic: p.is_synthetic, banner: p.banner,
    },
    data: {
      bettable: (raw.data?.bettable ?? []).map(mapValueBet),
      filtered: (raw.data?.filtered ?? []).map(mapValueBet),
      coverageGaps: (raw.data?.coverage_gaps ?? []).map(mapValueGap),
    },
  };
}
