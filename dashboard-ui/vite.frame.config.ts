import { resolve } from 'node:path';
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte({ hot: false })],
  resolve: { conditions: ['browser'] },
  publicDir: false,
  build: {
    outDir: 'dist-embed',
    emptyOutDir: false,
    rollupOptions: {
      input: resolve(__dirname, 'embed-frame.html'),
      output: {
        entryFileNames: 'wc-embed-frame.js',
        assetFileNames: (asset) =>
          asset.name?.endsWith('.css') ? 'wc-embed-frame.css' : 'assets/[name]-[hash][extname]',
      },
    },
  },
});
