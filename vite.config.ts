import { defineConfig } from "vite";
import { sveltekit } from "@sveltejs/kit/vite";

export default defineConfig({
  plugins: [sveltekit()],

  // Tauri expects a fixed port in dev
  server: {
    port: 5173,
    strictPort: true,
  },

  // Tauri env variables
  envPrefix: ["VITE_", "TAURI_"],

  build: {
    // Tauri supports es2021
    target: process.env.TAURI_PLATFORM === "windows" ? "chrome105" : "safari15",
    // Debug builds
    minify: !process.env.TAURI_DEBUG ? "esbuild" : false,
    sourcemap: !!process.env.TAURI_DEBUG,
  },
});
