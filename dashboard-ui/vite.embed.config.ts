import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte({ hot: false })],
  resolve: { conditions: ['browser'] },
  publicDir: false,
  build: {
    outDir: 'dist-embed',
    emptyOutDir: true,
    lib: {
      entry: 'src/embed/embed.ts',
      name: 'WCEmbed',
      formats: ['iife'],
      fileName: () => 'wc-embed.js',
    },
    rollupOptions: { output: { assetFileNames: 'wc-embed.[ext]' } },
  },
});
