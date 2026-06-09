import { parseHash } from '../../src/lib/router';

test('parseHash decodes valid match ids (existing behavior preserved)', () => {
  expect(parseHash('#/match/Brazil__Argentina__2024-05-01')).toEqual({
    name: 'match',
    id: 'Brazil__Argentina__2024-05-01',
  });
  // percent-encoded spaces decode to the real id
  expect(parseHash('#/match/Foo%20Bar')).toEqual({ name: 'match', id: 'Foo Bar' });
});

test('parseHash routes the non-match hashes; the EMPTY hash lands on Value (primary)', () => {
  // Value Bets is now the PRIMARY/default surface: the empty/root hash lands there.
  expect(parseHash('#/')).toEqual({ name: 'value' });
  expect(parseHash('')).toEqual({ name: 'value' });
  // The model surfaces are reachable but SECONDARY (under "Forecast").
  expect(parseHash('#/schedule')).toEqual({ name: 'schedule' });
  expect(parseHash('#/tournament')).toEqual({ name: 'tournament' });
  expect(parseHash('#/track')).toEqual({ name: 'track' });
});

test('parseHash does NOT throw on a malformed percent-escape (URIError guard)', () => {
  // A bare/incomplete percent escape makes decodeURIComponent throw URIError.
  // The shell must never crash on a bad hash — it falls back gracefully.
  expect(() => parseHash('#/match/100%')).not.toThrow();
  const route = parseHash('#/match/100%');
  // Either a match route with the raw (undecoded) id, or the default Value surface —
  // never an exception.
  if (route.name === 'match') {
    expect(route.id).toBe('100%'); // raw slice fallback
  } else {
    expect(route.name).toBe('value');
  }
});
