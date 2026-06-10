import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy API + WebSocket to the FastAPI backend during dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true, ws: true },
    },
  },
});
