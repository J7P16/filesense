<script lang="ts">
  import { onMount } from "svelte";

  let { children } = $props();

  onMount(() => {
    // Prevent default context menu in production
    if (!import.meta.env.DEV) {
      document.addEventListener("contextmenu", (e) => e.preventDefault());
    }

    // Disable text selection (it's a utility app, not a document)
    document.body.style.userSelect = "none";
    document.body.style.webkitUserSelect = "none";
  });
</script>

<svelte:head>
  <style>
    :root {
      --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", system-ui, sans-serif;
    }

    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }

    html, body {
      background: #fff;
      font-family: var(--font);
      color: #1d1d1f;
      overflow: hidden;
      -webkit-font-smoothing: antialiased;
      min-height: 100vh;
    }
  </style>
</svelte:head>

{@render children()}
