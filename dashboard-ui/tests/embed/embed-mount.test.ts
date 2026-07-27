import { afterEach, describe, expect, it, vi } from 'vitest';
import { mountEmbed } from '../../src/embed/embed';

const META = {
  data: {
    markets: [
      'win_group',
      'advance_from_group',
      'reach_r16',
      'reach_qf',
      'reach_sf',
      'reach_final',
      'champion',
    ],
  },
  provenance: {
    as_of: '2027-01-07T00:00:00Z',
    banner: 'Model forecasts · probabilities, not picks · not betting advice',
  },
};
const TOURNAMENT = {
  data: {
    Japan: {
      champion: { value: 0.2, se: 0.01 },
      win_group: { value: 0.5, se: 0.01 },
      advance_from_group: { value: 0.8, se: 0.01 },
      reach_r16: { value: 0.8, se: 0.01 },
      reach_qf: { value: 0.5, se: 0.01 },
      reach_sf: { value: 0.35, se: 0.01 },
      reach_final: { value: 0.25, se: 0.01 },
    },
  },
};
const SCHEDULE = { data: { group: [], knockout: [] } };

function stubGateway() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: RequestInfo | URL) => {
      const rendered = String(url);
      if (rendered.includes('/v1/token')) {
        return new Response(
          JSON.stringify({ token: 'p.9999999999.s', exp: 9_999_999_999, tier: 'basic' }),
        );
      }
      if (rendered.includes('meta.json')) return new Response(JSON.stringify(META));
      if (rendered.includes('tournament.json')) return new Response(JSON.stringify(TOURNAMENT));
      if (rendered.includes('schedule.json')) return new Response(JSON.stringify(SCHEDULE));
      throw new Error(`unexpected ${rendered}`);
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe('embed mount', () => {
  it('mounts the ladder, applies theme, shows normalized provenance, and destroys', async () => {
    stubGateway();
    const host = document.createElement('div');
    document.body.appendChild(host);
    const instance = mountEmbed(host, {
      endpoint: 'https://gw.example',
      publisherId: 'p',
      tournament: 'ac2027',
      theme: { '--accent': 'rgb(200, 0, 0)' },
    });
    await vi.waitFor(() => expect(host.textContent).toContain('Japan'));
    const container = host.querySelector('.wc-embed') as HTMLElement;
    expect(container).toBeTruthy();
    expect(container.style.getPropertyValue('--accent')).toBe('rgb(200, 0, 0)');
    expect(host.textContent).toContain(META.provenance.banner);
    expect(host.textContent).toContain('as-of 2027-01-07T00:00:00Z');
    expect(host.textContent).not.toMatch(/SYNTHETIC ODDS/);
    instance.destroy();
    await vi.waitFor(() => expect(host.querySelector('.wc-embed')).toBeNull());
  });

  it('does not read or write location.hash and adds no hash listeners', async () => {
    stubGateway();
    const addSpy = vi.spyOn(window, 'addEventListener');
    const host = document.createElement('div');
    document.body.appendChild(host);
    const before = location.hash;
    mountEmbed(host, { endpoint: 'https://gw.example', publisherId: 'p', tournament: 'ac2027' });
    await vi.waitFor(() => expect(host.textContent).toContain('Japan'));
    expect(location.hash).toBe(before);
    expect(addSpy.mock.calls.filter(([event]) => event === 'hashchange')).toHaveLength(0);
  });

  it('retains table rows under documented hostile host selectors', async () => {
    stubGateway();
    const style = document.createElement('style');
    style.textContent = 'table{display:none!important} .card{color:red!important} *{margin:99px!important}';
    document.head.appendChild(style);
    const host = document.createElement('div');
    document.body.appendChild(host);
    mountEmbed(host, { endpoint: 'https://gw.example', publisherId: 'p', tournament: 'ac2027' });
    await vi.waitFor(() => expect(host.querySelectorAll('.wc-embed table tbody tr').length).toBe(1));
    style.remove();
  });
});
