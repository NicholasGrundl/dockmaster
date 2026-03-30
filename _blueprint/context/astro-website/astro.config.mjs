// @ts-check
import { defineConfig } from 'astro/config';
import node from '@astrojs/node';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  // Produce a server build (SSR)
  output: 'server',

  // Node adapter (standalone bundles minimal deps into dist)
  adapter: node({
    mode: 'standalone'
  }),

  // Make the dev/prod server bind correctly inside Docker
  server: {
    host: true,                              // respect HOST=0.0.0.0
    port: Number(process.env.PORT) || 4321   // matches your Dockerfile/Caddy plan
  },

  // Keep your Tailwind via Vite plugin
  vite: {
    plugins: [tailwindcss()]
  }
});
