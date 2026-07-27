import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createClient } from '../../src/embed/client';

const TOK = { token: 'p.9999999999.sig', exp: 9_999_999_999, tier: 'advanced' as const };

function stubFetch(routes: Record<string, () => Response>) {
  return vi.fn(async (url: RequestInfo | URL) => {
    const rendered = String(url);
    for (const [needle, response] of Object.entries(routes)) {
      if (rendered.includes(needle)) return response();
    }
    throw new Error(`unexpected fetch ${rendered}`);
  });
}

describe('embed client', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('fetches a token once and reuses it for data calls', async () => {
    const fetchMock = stubFetch({
      '/v1/token': () => new Response(JSON.stringify(TOK)),
      '/v1/bundle/ac2027/meta.json': () =>
        new Response(JSON.stringify({ data: { markets: [] } })),
    });
    vi.stubGlobal('fetch', fetchMock);
    const client = createClient('https://gw.example', 'p');
    await client.getJson('/v1/bundle/ac2027/meta.json');
    await client.getJson('/v1/bundle/ac2027/meta.json');
    const tokenCalls = fetchMock.mock.calls.filter(([url]) =>
      String(url).includes('/v1/token'),
    );
    expect(tokenCalls).toHaveLength(1);
    expect(String(fetchMock.mock.calls.at(-1)![0])).toContain('t=p.9999999999.sig');
  });

  it('shares one in-flight token request across parallel surface loads', async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const rendered = String(url);
      if (rendered.includes('/v1/token')) {
        await gate;
        return new Response(JSON.stringify(TOK));
      }
      return new Response(JSON.stringify({ data: {} }));
    });
    vi.stubGlobal('fetch', fetchMock);
    const client = createClient('https://gw.example', 'p');
    const loads = Promise.all([
      client.getJson('/v1/bundle/ac2027/meta.json'),
      client.getJson('/v1/bundle/ac2027/tournament.json'),
      client.getJson('/v1/bundle/ac2027/schedule.json'),
    ]);
    await vi.waitFor(() => {
      expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/v1/token'))).toHaveLength(1);
    });
    release();
    await loads;
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/v1/token'))).toHaveLength(1);
  });

  it('retries once with a fresh token on 403', async () => {
    let dataHits = 0;
    const fetchMock = stubFetch({
      '/v1/token': () => new Response(JSON.stringify(TOK)),
      '/v1/bundle/ac2027/schedule.json': () =>
        ++dataHits === 1
          ? new Response('{"error":"auth"}', { status: 403 })
          : new Response(JSON.stringify({ data: { group: [] } })),
    });
    vi.stubGlobal('fetch', fetchMock);
    const client = createClient('https://gw.example', 'p');
    const output = await client.getJson<{ data: { group: unknown[] } }>(
      '/v1/bundle/ac2027/schedule.json',
    );
    expect(output.data.group).toEqual([]);
    expect(dataHits).toBe(2);
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/v1/token'))).toHaveLength(2);
  });

  it('never touches cookies or storage', async () => {
    vi.stubGlobal('fetch', stubFetch({ '/v1/token': () => new Response(JSON.stringify(TOK)) }));
    const storageSpy = vi.spyOn(Storage.prototype, 'setItem');
    const client = createClient('https://gw.example', 'p');
    await client.getToken();
    expect(storageSpy).not.toHaveBeenCalled();
    expect(document.cookie).toBe('');
  });
});
