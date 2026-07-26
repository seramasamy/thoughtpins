import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/app/",
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      "/v1": {
        target: "http://127.0.0.1:8420",
        changeOrigin: true,
      },
      "/health": {
        target: "http://127.0.0.1:8420",
        changeOrigin: true,
      },
      "/api": {
        target: "http://127.0.0.1:8420",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
