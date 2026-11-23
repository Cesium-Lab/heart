import { defineConfig } from "astro/config";

export default defineConfig({
  vite: {
    server: {
      // LAN names so the dev server works from psyche at http://mr-ray:4321
      allowedHosts: ["cesiumlab.net", "www.cesiumlab.net", "mr-ray"],
      proxy: {
        "/api/rotation": {
          target: "http://127.0.0.1:5001",
          changeOrigin: true,
        },
        "/api/setlister": {
          target: "http://127.0.0.1:5702",
          changeOrigin: true,
        },
      },
    },
  },
});
