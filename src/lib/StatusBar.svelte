<!--
  StatusBar — Shows indexing status at the bottom of the search window.
  Polls the Python sidecar every 5 seconds for stats.
-->
<script lang="ts">
  import { onMount, onDestroy } from "svelte";

  interface Status {
    total_files: number;
    indexed_files: number;
    total_chunks: number;
    failed_files: number;
    queue_size: number;
    pending_debounce: number;
    is_running: boolean;
    provider: string;
  }

  let { onSettingsClick = () => {} } = $props();

  let status = $state<Status | null>(null);
  let connected = $state(false);
  let interval: ReturnType<typeof setInterval>;

  const API_BASE = "http://127.0.0.1:9274/api";

  async function fetchStatus() {
    try {
      const res = await fetch(`${API_BASE}/status`);
      status = await res.json();
      connected = true;
    } catch {
      connected = false;
      status = null;
    }
  }

  onMount(() => {
    fetchStatus();
    interval = setInterval(fetchStatus, 5000);
  });

  onDestroy(() => {
    clearInterval(interval);
  });

  function isIndexing(): boolean {
    if (!status) return false;
    return status.queue_size > 0 || status.pending_debounce > 0;
  }
</script>

<div class="status-bar">
  {#if !connected}
    <span class="dot dot-error"></span>
    <span>Connecting to engine...</span>
  {:else if status}
    <span class="dot" class:dot-active={isIndexing()} class:dot-idle={!isIndexing()}></span>
    {#if isIndexing()}
      <span>Indexing... {status.queue_size} files queued</span>
    {:else}
      <span>{status.indexed_files.toLocaleString()} files · {status.total_chunks.toLocaleString()} chunks</span>
    {/if}
    <span class="provider">{status.provider}</span>
    <button class="settings-btn" onclick={onSettingsClick} aria-label="Settings">⚙</button>
  {/if}
</div>

<style>
  .status-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 18px;
    font-size: 11px;
    color: rgba(255, 255, 255, 0.35);
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    background: rgba(20, 20, 20, 0.6);
    border-radius: 0 0 12px 12px;
  }

  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .dot-active {
    background: #f5a623;
    animation: pulse 1.5s ease-in-out infinite;
  }

  .dot-idle {
    background: #6dd58c;
  }

  .dot-error {
    background: #e55;
    animation: pulse 1s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  .provider {
    margin-left: auto;
    opacity: 0.6;
  }

  .settings-btn {
    background: none;
    border: none;
    color: rgba(255, 255, 255, 0.35);
    font-size: 14px;
    cursor: pointer;
    padding: 0 2px;
    margin-left: 8px;
    transition: color 0.15s;
  }
  .settings-btn:hover {
    color: rgba(255, 255, 255, 0.7);
  }
</style>
