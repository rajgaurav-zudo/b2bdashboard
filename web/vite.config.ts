import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,               // reachable from outside the container
    port: 5173,
    strictPort: true,
    // virtiofs emits no inotify events under colima
    watch: { usePolling: true, interval: 300 },
    proxy: { "/api": { target: process.env.API_ORIGIN ?? "http://localhost:8000", changeOrigin: true } },
  },
});
