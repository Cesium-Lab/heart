import { defineConfig } from 'astro/config';

export default defineConfig({
  vite: {
    server: {
      allowedHosts: ['cesiumlab.net', 'www.cesiumlab.net'],
      proxy: {
        '/api/rotation': {
          target: 'http://127.0.0.1:5001',
          changeOrigin: true,
        },
        '/api/telemetry': {
          target: 'http://127.0.0.1:5701',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/telemetry/, ''),
        },
      },
    },
  },
});
