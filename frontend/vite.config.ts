import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // The MVP backend registers no CORS middleware, so the dev server proxies
  // /api to it and the browser only ever talks to its own origin.
  const target = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000';
  const port = Number(env.VITE_PORT) || 5173;

  return {
    plugins: [react()],
    server: {
      port,
      proxy: { '/api': { target, changeOrigin: true } },
    },
    preview: {
      port,
      proxy: { '/api': { target, changeOrigin: true } },
    },
  };
});
