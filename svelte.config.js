import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),

  kit: {
    // Static adapter for Tauri (outputs to /dist)
    adapter: adapter({
      fallback: "index.html",
    }),
  },
};

export default config;
