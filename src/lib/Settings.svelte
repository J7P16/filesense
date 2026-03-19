<!--
  Settings Panel

  Slide-in settings overlay for configuring:
    - Watched directories
    - Embedding provider (local vs cloud)
    - Search preferences
    - Indexing controls
-->
<script lang="ts">
  import { onMount } from "svelte";

  // --- Types ---
  interface IndexStatus {
    total_files: number;
    indexed_files: number;
    total_chunks: number;
    failed_files: number;
    queue_size: number;
    pending_debounce: number;
    is_running: boolean;
    provider: string;
  }

  // --- Props ---
  let { visible = $bindable(false) } = $props();

  // --- State ---
  let status = $state<IndexStatus | null>(null);
  let embeddingProvider = $state<"local" | "openai">("local");
  let openaiKey = $state("");
  let watchDirs = $state<string[]>([]);
  let newDir = $state("");
  let isSaving = $state(false);
  let saveMessage = $state("");

  const API_BASE = "http://127.0.0.1:9274/api";

  async function fetchStatus() {
    try {
      const res = await fetch(`${API_BASE}/status`);
      status = await res.json();
    } catch {
      status = null;
    }
  }

  async function triggerReindex() {
    for (const dir of watchDirs) {
      try {
        await fetch(`${API_BASE}/reindex?path=${encodeURIComponent(dir)}`, {
          method: "POST",
        });
      } catch (err) {
        console.error("Reindex failed:", err);
      }
    }
    saveMessage = "Re-indexing started...";
    setTimeout(() => (saveMessage = ""), 3000);
    fetchStatus();
  }

  function addDirectory() {
    const trimmed = newDir.trim();
    if (trimmed && !watchDirs.includes(trimmed)) {
      watchDirs = [...watchDirs, trimmed];
      newDir = "";
    }
  }

  function removeDirectory(dir: string) {
    watchDirs = watchDirs.filter((d) => d !== dir);
  }

  function formatBytes(bytes: number): string {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  }

  onMount(() => {
    fetchStatus();
    // Default watch directories
    watchDirs = [
      `${getHomeDir()}/Documents`,
      `${getHomeDir()}/Desktop`,
      `${getHomeDir()}/Downloads`,
    ];
  });

  function getHomeDir(): string {
    // In production, this comes from the Tauri API
    return "/Users/you";
  }

  function close() {
    visible = false;
  }
</script>

{#if visible}
  <!-- Backdrop -->
  <button class="backdrop" onclick={close} aria-label="Close settings"></button>

  <div class="panel" role="dialog" aria-label="Settings">
    <div class="panel-header">
      <h2>Settings</h2>
      <button class="close-btn" onclick={close} aria-label="Close">&times;</button>
    </div>

    <div class="panel-body">
      <!-- Index Status -->
      <section>
        <h3>Index status</h3>
        {#if status}
          <div class="stat-grid">
            <div class="stat">
              <span class="stat-value">{status.indexed_files.toLocaleString()}</span>
              <span class="stat-label">Files indexed</span>
            </div>
            <div class="stat">
              <span class="stat-value">{status.total_chunks.toLocaleString()}</span>
              <span class="stat-label">Chunks stored</span>
            </div>
            <div class="stat">
              <span class="stat-value">{status.failed_files}</span>
              <span class="stat-label">Failed</span>
            </div>
            <div class="stat">
              <span class="stat-value">{status.queue_size}</span>
              <span class="stat-label">In queue</span>
            </div>
          </div>
          <div class="provider-badge">
            Provider: <strong>{status.provider}</strong>
          </div>
        {:else}
          <p class="muted">Unable to connect to engine.</p>
        {/if}
      </section>

      <!-- Watched Directories -->
      <section>
        <h3>Watched directories</h3>
        <p class="hint">FileSense indexes files in these folders and their subfolders.</p>
        <div class="dir-list">
          {#each watchDirs as dir}
            <div class="dir-item">
              <span class="dir-path">{dir}</span>
              <button class="remove-btn" onclick={() => removeDirectory(dir)}>×</button>
            </div>
          {/each}
        </div>
        <div class="add-dir">
          <input
            type="text"
            placeholder="/path/to/folder"
            bind:value={newDir}
            onkeydown={(e) => e.key === "Enter" && addDirectory()}
          />
          <button class="add-btn" onclick={addDirectory}>Add</button>
        </div>
      </section>

      <!-- Embedding Provider -->
      <section>
        <h3>Embedding model</h3>
        <p class="hint">Choose how files are converted to searchable vectors.</p>

        <div class="radio-group">
          <label class="radio-option" class:selected={embeddingProvider === "local"}>
            <input
              type="radio"
              name="provider"
              value="local"
              bind:group={embeddingProvider}
            />
            <div>
              <strong>Local (recommended)</strong>
              <span class="option-desc">
                MiniLM model runs on your Mac. Free, private, no internet needed.
                ~500 files/sec on Apple Silicon.
              </span>
            </div>
          </label>

          <label class="radio-option" class:selected={embeddingProvider === "openai"}>
            <input
              type="radio"
              name="provider"
              value="openai"
              bind:group={embeddingProvider}
            />
            <div>
              <strong>OpenAI API</strong>
              <span class="option-desc">
                Higher quality embeddings for nuanced queries. Requires API key.
                ~$0.02 per million tokens.
              </span>
            </div>
          </label>
        </div>

        {#if embeddingProvider === "openai"}
          <div class="api-key-input">
            <label for="openai-key">API key</label>
            <input
              id="openai-key"
              type="password"
              placeholder="sk-..."
              bind:value={openaiKey}
            />
            <p class="warning">
              Switching providers requires a full re-index. File content will be
              sent to OpenAI's API for embedding.
            </p>
          </div>
        {/if}
      </section>

      <!-- Actions -->
      <section>
        <h3>Actions</h3>
        <div class="actions">
          <button class="action-btn" onclick={triggerReindex}>
            Re-index all files
          </button>
          <button class="action-btn secondary" onclick={fetchStatus}>
            Refresh status
          </button>
        </div>
        {#if saveMessage}
          <p class="save-msg">{saveMessage}</p>
        {/if}
      </section>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 90;
    border: none;
    cursor: default;
  }

  .panel {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 380px;
    background: rgba(28, 28, 28, 0.98);
    border-left: 1px solid rgba(255, 255, 255, 0.08);
    z-index: 100;
    display: flex;
    flex-direction: column;
    animation: slideIn 0.2s ease-out;
    backdrop-filter: blur(40px);
  }

  @keyframes slideIn {
    from { transform: translateX(100%); }
    to { transform: translateX(0); }
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 18px 20px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  h2 {
    font-size: 16px;
    font-weight: 600;
    color: #f0f0f0;
  }

  .close-btn {
    background: none;
    border: none;
    color: rgba(255, 255, 255, 0.5);
    font-size: 22px;
    cursor: pointer;
    padding: 0 4px;
    line-height: 1;
  }
  .close-btn:hover { color: #fff; }

  .panel-body {
    flex: 1;
    overflow-y: auto;
    padding: 16px 20px;
  }

  section {
    margin-bottom: 28px;
  }

  h3 {
    font-size: 13px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.7);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 10px;
  }

  .hint {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.35);
    margin-bottom: 12px;
    line-height: 1.4;
  }

  .muted {
    font-size: 13px;
    color: rgba(255, 255, 255, 0.3);
  }

  /* Stat grid */
  .stat-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 10px;
  }

  .stat {
    background: rgba(255, 255, 255, 0.04);
    border-radius: 8px;
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
  }

  .stat-value {
    font-size: 18px;
    font-weight: 600;
    color: #f0f0f0;
  }

  .stat-label {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.4);
    margin-top: 2px;
  }

  .provider-badge {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.45);
  }
  .provider-badge strong {
    color: #6dd58c;
  }

  /* Directories */
  .dir-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 10px;
  }

  .dir-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    background: rgba(255, 255, 255, 0.04);
    border-radius: 6px;
    font-size: 12px;
  }

  .dir-path {
    color: rgba(255, 255, 255, 0.6);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .remove-btn {
    background: none;
    border: none;
    color: rgba(255, 255, 255, 0.3);
    cursor: pointer;
    font-size: 16px;
    padding: 0 4px;
    flex-shrink: 0;
  }
  .remove-btn:hover { color: #e55; }

  .add-dir {
    display: flex;
    gap: 8px;
  }

  .add-dir input {
    flex: 1;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 12px;
    color: #f0f0f0;
    outline: none;
    font-family: inherit;
  }
  .add-dir input:focus {
    border-color: rgba(255, 255, 255, 0.2);
  }

  .add-btn {
    background: rgba(109, 213, 140, 0.15);
    color: #6dd58c;
    border: none;
    border-radius: 6px;
    padding: 7px 14px;
    font-size: 12px;
    cursor: pointer;
    font-weight: 500;
  }
  .add-btn:hover {
    background: rgba(109, 213, 140, 0.25);
  }

  /* Radio options */
  .radio-group {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .radio-option {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    cursor: pointer;
    transition: border-color 0.15s;
  }

  .radio-option.selected {
    border-color: rgba(109, 213, 140, 0.3);
    background: rgba(109, 213, 140, 0.04);
  }

  .radio-option input[type="radio"] {
    margin-top: 3px;
    accent-color: #6dd58c;
  }

  .radio-option strong {
    font-size: 13px;
    color: #f0f0f0;
    display: block;
  }

  .option-desc {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.4);
    line-height: 1.4;
    display: block;
    margin-top: 3px;
  }

  /* API key input */
  .api-key-input {
    margin-top: 12px;
  }

  .api-key-input label {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.5);
    display: block;
    margin-bottom: 6px;
  }

  .api-key-input input {
    width: 100%;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 13px;
    color: #f0f0f0;
    outline: none;
    font-family: var(--font-mono, monospace);
  }

  .warning {
    font-size: 11px;
    color: #f5a623;
    margin-top: 8px;
    line-height: 1.4;
  }

  /* Actions */
  .actions {
    display: flex;
    gap: 8px;
  }

  .action-btn {
    flex: 1;
    padding: 9px 14px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    border: none;
    background: rgba(109, 213, 140, 0.15);
    color: #6dd58c;
    font-family: inherit;
  }
  .action-btn:hover {
    background: rgba(109, 213, 140, 0.25);
  }

  .action-btn.secondary {
    background: rgba(255, 255, 255, 0.06);
    color: rgba(255, 255, 255, 0.6);
  }
  .action-btn.secondary:hover {
    background: rgba(255, 255, 255, 0.1);
  }

  .save-msg {
    font-size: 12px;
    color: #6dd58c;
    margin-top: 8px;
  }
</style>
