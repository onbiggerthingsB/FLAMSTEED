export type Route =
  | { name: 'schedule' }
  | { name: 'tournament' }
  | { name: 'track' }
  | { name: 'match'; id: string };

export function parseHash(hash: string): Route {
  const h = hash.replace(/^#\/?/, '');
  if (h.startsWith('match/')) return { name: 'match', id: decodeURIComponent(h.slice('match/'.length)) };
  if (h === 'tournament') return { name: 'tournament' };
  if (h === 'track') return { name: 'track' };
  return { name: 'schedule' };
}
