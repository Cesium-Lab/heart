import { defineConfig } from "astro/config";

export default defineConfig({
  // Dev server port: 42800, the development range in architecture/services.md.
  server: { port: 42800 },
  // The map used to live at /planes/map/; the board is now a drawer on it.
  redirects: { "/planes/map": "/planes/" },
  vite: {
    server: {
      // LAN names so the dev server works from psyche at http://mr-ray:42800
      allowedHosts: ["cesiumlab.net", "www.cesiumlab.net", "mr-ray"],
      proxy: {
        "/api/rotation": {
          target: "http://127.0.0.1:42902",
          changeOrigin: true,
        },
        "/inbox": {
          target: "http://127.0.0.1:42904",
          changeOrigin: true,
        },
        "/tasks": {
          target: "http://127.0.0.1:42906",
          changeOrigin: true,
        },
        "/hq": {
          target: "http://127.0.0.1:42907",
          changeOrigin: true,
        },
        "/api/planes": {
          target: "http://127.0.0.1:42901",
          changeOrigin: true,
        },
        "/api/setlister": {
          target: "http://127.0.0.1:42903",
          changeOrigin: true,
        },
      },
    },
  },
});
