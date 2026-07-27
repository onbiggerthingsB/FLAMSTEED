import { fireEvent } from '@testing-library/dom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mountEmbed } from '../../src/embed/embed';
import { assertNoNakedNumbers } from '../helpers/guard';

const FIXTURE_ROOT = resolve(__dirname, '../fixtures/bundle');
const readFixture = (relative: string) =>
  JSON.parse(readFileSync(resolve(FIXTURE_ROOT, relative), 'utf8'));
const META = {
  ...readFixture('meta.json'),
  provenance: {
    as_of: '2027-01-07T00:00:00Z',
    banner: 'Model forecasts · probabilities, not picks · not betting advice',
  },
};
const SCHEDULE = readFixture('schedule.json');
const TOURNAMENT = readFixture('tournament.json');
const MATCH_ID = 'Brazil__Argentina__2024-05-01';
const DETAIL = readFixture(`fixtures/${MATCH_ID}.json`);
const GATEWAY = 'https://gateway.example';
const FORBIDDEN = /\b(odds|stake|bet|edge|kelly|bookmaker|wager|clv)\b/i;

function stubGateway() {
  const urls: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      urls.push(url);
      if (url.includes('/v1/token')) {
        return new Response(
          JSON.stringify({
            token: 'daily-news.9999999999.signature',
            exp: 9_999_999_999,
            tier: 'advanced',
          }),
        );
      }
      if (url.includes('/meta.json')) return new Response(JSON.stringify(META));
      if (url.includes('/schedule.json')) return new Response(JSON.stringify(SCHEDULE));
      if (url.includes('/tournament.json')) return new Response(JSON.stringify(TOURNAMENT));
      if (url.includes(`/fixtures/${MATCH_ID}.json`)) {
        return new Response(JSON.stringify(DETAIL));
      }
      throw new Error(`unexpected gateway request: ${url}`);
    }),
  );
  return urls;
}

function expectGuarded(host: HTMLElement) {
  const embed = host.querySelector('.wc-embed') as HTMLElement;
  expect(embed).toBeTruthy();
  assertNoNakedNumbers(embed);
  expect(embed.querySelectorAll('form')).toHaveLength(0);
  expect(embed.textContent ?? '').not.toMatch(FORBIDDEN);
  expect(embed.querySelector('.wc-embed-foot')).toBeTruthy();
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe('publisher embed guard', () => {
  it('guards ladder and schedule surfaces and confines every fetch to the gateway', async () => {
    const urls = stubGateway();
    for (const surface of ['ladder', 'schedule'] as const) {
      const host = document.createElement('div');
      document.body.appendChild(host);
      const instance = mountEmbed(host, {
        endpoint: GATEWAY,
        publisherId: 'daily-news',
        tournament: 'ac2027',
        surface,
      });
      await vi.waitFor(() => expect(host.querySelector('.wc-embed-foot')).toBeTruthy());
      expectGuarded(host);
      instance.destroy();
      host.remove();
    }
    expect(urls.length).toBeGreaterThan(0);
    expect(urls.every((url) => url.startsWith(`${GATEWAY}/`))).toBe(true);
  });

  it('does not submit an ancestor form when opening a row or going back', async () => {
    const urls = stubGateway();
    const ancestor = document.createElement('form');
    const host = document.createElement('div');
    ancestor.appendChild(host);
    document.body.appendChild(ancestor);
    const submit = vi.fn((event: SubmitEvent) => event.preventDefault());
    ancestor.addEventListener('submit', submit);

    const instance = mountEmbed(host, {
      endpoint: GATEWAY,
      publisherId: 'daily-news',
      tournament: 'ac2027',
      surface: 'schedule',
    });
    const detailButton = await vi.waitFor(() => {
      const button = host.querySelector(
        `button[data-match-id="${MATCH_ID}"]`,
      ) as HTMLButtonElement | null;
      expect(button).toBeTruthy();
      return button as HTMLButtonElement;
    });
    expect(detailButton.type).toBe('button');
    await fireEvent.click(detailButton);
    await vi.waitFor(() => expect(host.textContent).toContain('Most likely score'));
    expectGuarded(host);

    const back = host.querySelector('button[data-embed-back]') as HTMLButtonElement;
    expect(back).toBeTruthy();
    expect(back.type).toBe('button');
    await fireEvent.click(back);
    await vi.waitFor(() => expect(host.querySelector('button[data-embed-back]')).toBeNull());

    expect(submit).not.toHaveBeenCalled();
    expect(urls.every((url) => url.startsWith(`${GATEWAY}/`))).toBe(true);
    expectGuarded(host);
    instance.destroy();
  });
});
