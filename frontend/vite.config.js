import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Prod: `npm run build` → frontend/dist, served by FastAPI on :8007.
// Dev: `npm run dev` (:5173) proxies /api → dashboard :8007.
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8007',
    },
  },
  plugins: [react()],
  css: {
    modules: {
      localsConvention: 'camelCase',
    },
  },
});
