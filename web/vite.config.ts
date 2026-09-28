import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";
import path from "node:path";

// `vite build --mode demo` produces one self-contained HTML file with a bundled data
// snapshot (no API needed) for sharing; the normal build talks to the FastAPI service.
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss(), ...(mode === "demo" ? [viteSingleFile()] : [])],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: {
    outDir: mode === "demo" ? "dist-demo" : "dist",
    target: "es2022",
    chunkSizeWarningLimit: 900,
    assetsInlineLimit: mode === "demo" ? 100_000_000 : 4096,
  },
}));
