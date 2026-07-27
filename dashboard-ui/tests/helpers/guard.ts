import { expect } from 'vitest';

export const PCT = /\d+(\.\d+)?\s*%/;

const EXEMPT = '[data-uncertainty], [data-coverage-gap], [data-derived], [data-estimate]';

/** The shared load-bearing guard; keep its assertions identical across callers. */
export function assertNoNakedNumbers(container: HTMLElement): void {
  container.querySelectorAll('[data-estimate]').forEach((est) => {
    const hasCompanion = est.querySelector('[data-uncertainty]') !== null;
    const isNullDash = (est.textContent ?? '').trim() === '—';
    const insideGap = est.closest('[data-coverage-gap]') !== null;
    expect(
      hasCompanion || isNullDash || insideGap,
      `naked estimate (no ± companion, not a — null): "${est.textContent?.trim()}"`,
    ).toBe(true);
  });

  container.querySelectorAll('*').forEach((el) => {
    const ownText = Array.from(el.childNodes)
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent)
      .join('');
    if (!PCT.test(ownText)) return;
    const ok = el.closest(EXEMPT) !== null || el.matches('[data-estimate]');
    expect(ok, `naked % text (outside ${EXEMPT}): "${ownText.trim()}"`).toBeTruthy();
  });

  container.querySelectorAll('[title], [aria-label]').forEach((el) => {
    for (const attr of ['title', 'aria-label'] as const) {
      const val = el.getAttribute(attr);
      if (!val || !PCT.test(val)) continue;
      const ok = el.closest(EXEMPT) !== null || el.matches('[data-estimate]');
      expect(ok, `naked % in @${attr} (outside ${EXEMPT}): "${val.trim()}"`).toBeTruthy();
    }
  });
}
