import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built into ../app/static so the FastAPI backend serves it (assets under /static/).
// `npm run dev` proxies the API to a backend on :8080.
// For GitHub Pages the workflow sets VITE_BASE=/<repo>/ and VITE_STATIC_API=1.
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE || "/static/",
  build: {
    outDir: "../app/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8080",
    },
  },
});
