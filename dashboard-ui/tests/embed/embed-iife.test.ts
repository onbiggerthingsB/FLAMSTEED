import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('built embed IIFE', () => {
  it.skipIf(!existsSync(resolve('dist-embed/wc-embed.js')))(
    'exposes the WCEmbed global with a mount property (build artifact required)',
    () => {
      const source = readFileSync(resolve('dist-embed/wc-embed.js'), 'utf8');
      expect(source).toMatch(/window\.WCEmbed|var WCEmbed/);
      expect(source).toMatch(/mount\s*[:=]/);
    },
  );
});
