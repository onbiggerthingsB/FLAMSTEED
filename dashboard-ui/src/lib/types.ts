// Typed mirror of the bundle JSON contract emitted by the Plan-1 serializer.
// The serializer is ground truth; these declarations follow the REAL committed
// fixture at tests/fixtures/bundle/. Every artifact is an envelope.

export interface Provenance {
  as_of: string;
  posterior_key: string;
  git: string;
  is_synthetic: boolean;
  n_sims: number;
  banner?: string; // present iff synthetic
}
export interface Envelope<T> {
  provenance: Provenance;
  data: T;
}

// A coverage gap can appear anywhere a value is unavailable. The serializer
// emits TWO shapes: the canonical `{coverage_gap, reason, value:null}` (track,
// why.xg, why.rest_days) and a leaner `{coverage_gap, reason}` on edge nodes
// (no `value` key). `value` is therefore optional to match both REAL shapes.
export interface Gap {
  coverage_gap: true;
  reason: string;
  value?: null;
}
export type Maybe<T> = T | Gap;

export interface ValueSe {
  value: number | null;
  se: number | null;
}
export interface ValueCi {
  value: number;
  ci: [number, number];
}

export interface MetaData {
  markets: string[];
  provenance_note: string;
}

// The serializer emits a market node only `if m in prog.columns`, so a given team may be
// MISSING any particular market key. Mirror that REAL conditional emission: the inner
// market map is partial (a key may be absent). Surfaces read it null-safely (`?.`).
export type TournamentData = Record<string, Partial<Record<string, ValueSe>>>;

export interface MostLikely {
  home_goals: number;
  away_goals: number;
  prob: number;
}
export interface OneXTwo {
  home: number;
  draw: number;
  away: number;
}
export interface ForecastSummary {
  most_likely: MostLikely;
  one_x_two: OneXTwo;
  // Spec D3: the row leads with the 1X2 split + the top-3 scoreline shortlist ("predicted
  // score = shortlist, never a lone score"). A pure projection of the gated forecast's
  // already-computed shortlist (top-3); the serializer GATES every entry's prob in [0,1].
  shortlist: MostLikely[];
  // GHOST LINE: the OPTIONAL de-vigged ENTRY market 1X2 — a DERIVED model-vs-market
  // comparison (the de-vig of the decision-time ENTRY odds the edge was priced against),
  // ghosted into the WinBar as the `line` prop. Present ONLY where a real (non-gap) edge
  // carries a valid line; the serializer omits it otherwise. NOT a forecast estimate — it
  // carries no ± companion (derived, by design); the WinBar renders it inside the marked
  // distribution region so the no-naked-number guard exempts it.
  market_1x2?: OneXTwo;
}
export interface EdgeNode {
  staked: 'home' | 'draw' | 'away';
  edge: number;
  stake_signal: number;
  entry_odds: number;
  is_synthetic: boolean;
  // GHOST LINE: the de-vigged ENTRY market 1X2 the edge was priced against (the DERIVED
  // model-vs-market comparison). Present only where the serializer emitted a valid line;
  // MatchDetail ghosts it into the WinBar as the `line` prop. No ± companion (derived).
  market_1x2?: OneXTwo;
}
export interface GroupRow {
  home: string;
  away: string;
  date: string;
  group: string | null;
  stage: 'group';
  status: 'played' | 'upcoming';
  forecast_summary: Maybe<ForecastSummary>;
  edge: Maybe<EdgeNode>;
  match_id: string;
}
export interface Occupant {
  team: string;
  prob: number;
  se: number;
}
export interface KoRow {
  match: number;
  // The serializer uses match_round.get() which can be None → stage may be null. Mirror it;
  // Schedule renders a placeholder when null (never a raw "null"/blank-with-separator).
  stage: string | null;
  status: 'upcoming';
  home_ref: string;
  away_ref: string;
  home_occupants: Maybe<Occupant[]>;
  away_occupants: Maybe<Occupant[]>;
}
export interface ScheduleData {
  group: GroupRow[];
  knockout: KoRow[];
}

export interface Forecast {
  home: string;
  away: string;
  most_likely: MostLikely;
  shortlist: MostLikely[];
  grid: number[][];
  one_x_two: OneXTwo;
}
export interface Strength {
  attack: ValueCi;
  defense: ValueCi;
}
export interface FormMatch {
  date: string;
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
}
export interface Form {
  matches: FormMatch[];
}
export interface Why {
  team_strength: { home: Strength; away: Strength };
  xg: { home: Maybe<{ value: number }>; away: Maybe<{ value: number }> };
  rest_days: { home: Maybe<{ value: number }>; away: Maybe<{ value: number }> };
  recent_form: { home: Maybe<Form>; away: Maybe<Form> };
}
export interface FixtureDetail {
  match_id: string;
  home: string;
  away: string;
  date: string;
  stage: string;
  forecast: Forecast;
  why: Why;
  edge: Maybe<EdgeNode>;
}

export interface ReliabilityBin {
  bin_lo: number;
  bin_hi: number;
  n: number;
  forecast_mean: number | null;
  empirical: number | null;
}
export interface TrackReal {
  n_bets: number;
  beat_close_rate: number | null;
  avg_clv: number | null;
  rps: { model: number | null; market: number | null; elo: number | null };
  reliability: ReliabilityBin[];
  is_synthetic: boolean;
}
export type TrackData = Maybe<TrackReal>;
