export type Route =
  | { name: 'value' }
  | { name: 'track' }
  | { name: 'schedule' }
  | { name: 'tournament' }
  | { name: 'match'; id: string };

// A malformed percent-escape (e.g. `#/match/100%`) makes decodeURIComponent throw
// URIError. An unguarded decode crashes the whole shell on a bad hash, so we fall
// back to the RAW id slice — a real fixture id never contains a stray `%`, so the
// fetch will simply 404 into the surface's error state instead of taking down the app.
function safeDecode(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch (e) {
    if (e instanceof URIError) return raw;
    throw e;
  }
}

// PRIMARY route is now "value" (the +EV value scanner). The model surfaces
// (schedule / tournament / match) are grouped under a SECONDARY "Forecast" nav,
// visibly labeled as an independent forecast that does NOT beat the market.
// "track" is the Track Record (realized-CLV scoreboard).
export function parseHash(hash: string): Route {
  const h = hash.replace(/^#\/?/, '');
  if (h.startsWith('match/')) return { name: 'match', id: safeDecode(h.slice('match/'.length)) };
  if (h === 'track') return { name: 'track' };
  if (h === 'schedule') return { name: 'schedule' };
  if (h === 'tournament') return { name: 'tournament' };
  return { name: 'value' };
}
