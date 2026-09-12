import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/feedback": { target: "ws://127.0.0.1:8000", ws: true },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
      "/health": "http://127.0.0.1:8000",
    },
  },
});
