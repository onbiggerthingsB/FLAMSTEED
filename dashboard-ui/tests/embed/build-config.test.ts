// @vitest-environment node

import { describe, expect, it } from 'vitest';
import embedConfig from '../../vite.embed.config';
import frameConfig from '../../vite.frame.config';

describe('embed build isolation', () => {
  it.each([
    ['embed', embedConfig],
    ['frame', frameConfig],
  ])('%s build excludes the flagship public directory', (_name, config) => {
    expect(config.publicDir).toBe(false);
  });

  it.each([
    ['embed', embedConfig],
    ['frame', frameConfig],
  ])('%s build does not write to the flagship dist directory', (_name, config) => {
    expect(config.build?.outDir).not.toBe('dist');
  });
});
