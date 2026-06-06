export type Route =
  | { name: 'schedule' }
  | { name: 'tournament' }
  | { name: 'track' }
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

export function parseHash(hash: string): Route {
  const h = hash.replace(/^#\/?/, '');
  if (h.startsWith('match/')) return { name: 'match', id: safeDecode(h.slice('match/'.length)) };
  if (h === 'tournament') return { name: 'tournament' };
  if (h === 'track') return { name: 'track' };
  return { name: 'schedule' };
}
