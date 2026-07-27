import { mount as mountSvelte, unmount } from 'svelte';
import EmbedApp from './EmbedApp.svelte';
import { createClient } from './client';
import './embed.css';

export interface EmbedOptions {
  endpoint: string;
  publisherId: string;
  tournament: string;
  surface?: 'ladder' | 'schedule';
  theme?: Record<string, string>;
}

export function mountEmbed(element: HTMLElement, options: EmbedOptions) {
  const client = createClient(options.endpoint, options.publisherId);
  const app = mountSvelte(EmbedApp, {
    target: element,
    props: {
      client,
      tournament: options.tournament,
      surface: options.surface ?? 'ladder',
      theme: options.theme ?? {},
    },
  });
  return {
    destroy() {
      void unmount(app);
    },
  };
}

export { mountEmbed as mount };
