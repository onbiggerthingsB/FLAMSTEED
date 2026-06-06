import type {
  Envelope, Provenance, ScheduleData, TournamentData, TrackData, MetaData, FixtureDetail,
} from './types';

export function unwrap<T>(e: Envelope<T>): T { return e.data; }
export function provenanceOf<T>(e: Envelope<T>): Provenance { return e.provenance; }

async function getJson<T>(url: string): Promise<Envelope<T>> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`failed to load ${url}: ${r.status}`);
  return (await r.json()) as Envelope<T>;
}

export interface Bundle {
  meta: Envelope<MetaData>;
  schedule: Envelope<ScheduleData>;
  tournament: Envelope<TournamentData>;
  track: Envelope<TrackData>;
}

export async function loadBundle(baseUrl: string): Promise<Bundle> {
  const b = baseUrl.replace(/\/$/, '');
  const [meta, schedule, tournament, track] = await Promise.all([
    getJson<MetaData>(`${b}/meta.json`),
    getJson<ScheduleData>(`${b}/schedule.json`),
    getJson<TournamentData>(`${b}/tournament.json`),
    getJson<TrackData>(`${b}/track.json`),
  ]);
  return { meta, schedule, tournament, track };
}

export function loadFixture(baseUrl: string, matchId: string): Promise<Envelope<FixtureDetail>> {
  return getJson<FixtureDetail>(`${baseUrl.replace(/\/$/, '')}/fixtures/${matchId}.json`);
}
