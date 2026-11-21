import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

// Django dev server (backend/). In production IIS proxies /api instead.
const api = { '/api': 'http://127.0.0.1:8020' };

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  server: { proxy: api },
  preview: { proxy: api }
});
