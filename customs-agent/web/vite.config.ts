import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs separately (uv run uvicorn app.api:app --port 8000).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
});
