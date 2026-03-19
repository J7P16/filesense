<!--
  FileSense Search UI — macOS Finder-inspired design
-->
<script lang="ts">
  import { onMount } from "svelte";

  interface SearchResult {
    file_path: string;
    file_name: string;
    file_type: string;
    snippet: string;
    similarity: number;
    final_score: number;
    last_modified: number;
    chunk_count: number;
  }

  interface SearchResponse {
    results: SearchResult[];
    query: string;
    elapsed_ms: number;
  }

  let query = $state("");
  let results = $state<SearchResult[]>([]);
  let isLoading = $state(false);
  let elapsedMs = $state(0);
  let selectedIndex = $state(0);
  let debounceTimer: ReturnType<typeof setTimeout>;
  let resultCount = $state(0);

  const API_BASE = "http://127.0.0.1:9274/api";

  function onInput() {
    clearTimeout(debounceTimer);
    if (!query.trim()) {
      results = [];
      resultCount = 0;
      return;
    }
    isLoading = true;
    debounceTimer = setTimeout(() => executeSearch(), 300);
  }

  async function executeSearch() {
    try {
      const res = await fetch(`${API_BASE}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: 100 }),
      });
      const data: SearchResponse = await res.json();
      results = data.results;
      resultCount = data.results.length;
      elapsedMs = data.elapsed_ms;
      selectedIndex = 0;
    } catch (err) {
      console.error("Search failed:", err);
      results = [];
      resultCount = 0;
    } finally {
      isLoading = false;
    }
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      selectedIndex = Math.min(selectedIndex + 1, results.length - 1);
      scrollToSelected();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      selectedIndex = Math.max(selectedIndex - 1, 0);
      scrollToSelected();
    } else if (e.key === "Enter" && results.length > 0) {
      e.preventDefault();
      openFile(results[selectedIndex]);
    } else if (e.key === "Escape") {
      query = "";
      results = [];
      resultCount = 0;
    }
  }

  function scrollToSelected() {
    const el = document.querySelector(".result-item.selected");
    el?.scrollIntoView({ block: "nearest" });
  }

  async function openFile(result: SearchResult) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("reveal_in_finder", { path: result.file_path });
    } catch {
      // Fallback for browser dev mode
      window.open(`file://${result.file_path}`);
    }
  }

  async function revealInFinder(result: SearchResult) {
    try {
      const { Command } = await import("@tauri-apps/plugin-shell");
      await Command.create("open", ["-R", result.file_path]).execute();
    } catch (err) {
      console.error("Failed to reveal:", err);
    }
  }

  function getExtension(fileType: string): string {
    return fileType.replace(".", "").toUpperCase();
  }

  function getExtColor(fileType: string): string {
    const colors: Record<string, string> = {
      ".pdf": "#E84E3F",
      ".docx": "#2B6CB0", ".doc": "#2B6CB0",
      ".pptx": "#D4652A", ".xlsx": "#1E7D48",
      ".csv": "#1E7D48", ".tsv": "#1E7D48",
      ".py": "#3572A5", ".js": "#D4A017", ".ts": "#2B6CB0",
      ".jsx": "#D4A017", ".tsx": "#2B6CB0",
      ".java": "#B07219", ".go": "#00ADD8", ".rs": "#DEA584",
      ".html": "#E44D26", ".css": "#1572B6",
      ".md": "#555", ".txt": "#777",
      ".json": "#555", ".yaml": "#555", ".yml": "#555",
      ".sql": "#E38C00",
      ".swift": "#FA7343", ".kt": "#A97BFF",
      ".tex": "#3D6117",
    };
    return colors[fileType] || "#888";
  }

  function formatDate(timestamp: number): string {
    const date = new Date(timestamp * 1000);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined });
  }

  function shortenPath(path: string): string {
    const home = "/Users/";
    let short = path;
    const homeIdx = short.indexOf(home);
    if (homeIdx !== -1) {
      const afterHome = short.substring(homeIdx + home.length);
      const slashIdx = afterHome.indexOf("/");
      if (slashIdx !== -1) {
        short = "~" + afterHome.substring(slashIdx);
      }
    }
    const lastSlash = short.lastIndexOf("/");
    if (lastSlash !== -1) {
      short = short.substring(0, lastSlash);
    }
    return short;
  }

  function formatScore(score: number): string {
    return `${Math.round(score * 100)}`;
  }

  onMount(() => {
    document.getElementById("search-input")?.focus();
  });
</script>

<div class="shell">
  <!-- Toolbar -->
  <div class="toolbar">
    <div class="toolbar-left">
      <span class="toolbar-title">FileSense</span>
    </div>
    <div class="search-wrap">
      <svg class="search-svg" width="13" height="13" viewBox="0 0 14 14" fill="none">
        <circle cx="5.5" cy="5.5" r="4.5" stroke="currentColor" stroke-width="1.5"/>
        <line x1="9" y1="9" x2="13" y2="13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
      <input
        id="search-input"
        type="text"
        placeholder="Search"
        bind:value={query}
        oninput={onInput}
        onkeydown={onKeydown}
        autocomplete="off"
        spellcheck="false"
      />
      {#if isLoading}
        <div class="loader"></div>
      {/if}
    </div>
  </div>

  <!-- Column Header -->
  {#if results.length > 0}
    <div class="col-header">
      <span class="col-name">Name</span>
      <span class="col-date">Date Modified</span>
      <span class="col-match">Relevance</span>
    </div>
  {/if}

  <!-- Results -->
  <div class="results-area">
    {#if results.length > 0}
      {#each results as result, i}
        <button
          class="result-item"
          class:selected={i === selectedIndex}
          class:even={i % 2 === 0}
          onclick={() => openFile(result)}
          ondblclick={() => revealInFinder(result)}
          oncontextmenu={(e) => { e.preventDefault(); revealInFinder(result); }}
          onmouseenter={() => (selectedIndex = i)}
        >
          <div class="file-icon-wrap">
            <svg class="file-svg" width="26" height="32" viewBox="0 0 28 34" fill="none">
              <path d="M2 1h16l8 8v24a1 1 0 01-1 1H2a1 1 0 01-1-1V2a1 1 0 011-1z" fill="#fff" stroke="#C4C4C4" stroke-width="0.75"/>
              <path d="M18 1v7a1 1 0 001 1h7" fill="#F0F0F0" stroke="#C4C4C4" stroke-width="0.75"/>
            </svg>
            <span class="ext-badge" style="background: {getExtColor(result.file_type)}">{getExtension(result.file_type)}</span>
          </div>

          <div class="file-info">
            <span class="file-name">{result.file_name}</span>
            <span class="file-loc">{shortenPath(result.file_path)}</span>
          </div>

          <span class="file-date">{formatDate(result.last_modified)}</span>
          <span class="file-score">{formatScore(result.final_score)}</span>
        </button>
      {/each}
    {:else if query.trim() && !isLoading}
      <div class="empty">
        <p class="empty-title">No Results</p>
        <p class="empty-sub">Try a different query. FileSense searches by meaning, not just keywords.</p>
      </div>
    {:else if !query.trim()}
      <div class="empty">
        <svg width="40" height="40" viewBox="0 0 40 40" fill="none" style="margin-bottom: 8px; opacity: 0.25;">
          <circle cx="16" cy="16" r="12" stroke="#888" stroke-width="2.5"/>
          <line x1="25" y1="25" x2="37" y2="37" stroke="#888" stroke-width="2.5" stroke-linecap="round"/>
        </svg>
        <p class="empty-title">Search your files</p>
        <p class="empty-sub">Find documents, code, and notes by what they contain.</p>
      </div>
    {/if}
  </div>

  <!-- Status bar -->
  <div class="statusbar">
    {#if results.length > 0}
      <span>{results.length} items found</span>
      <span class="status-right">{(elapsedMs / 1000).toFixed(1)}s</span>
    {:else}
      <span>Ready</span>
    {/if}
  </div>
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: #fff;
    color: #1d1d1f;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", system-ui, sans-serif;
    font-size: 13px;
    -webkit-font-smoothing: antialiased;
    letter-spacing: -0.01em;
  }

  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 12px;
    background: #F5F5F5;
    border-bottom: 1px solid #D4D4D4;
    gap: 12px;
    min-height: 38px;
  }

  .toolbar-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .toolbar-title {
    font-size: 13px;
    font-weight: 600;
    color: #333;
    letter-spacing: -0.02em;
  }

  .search-wrap {
    display: flex;
    align-items: center;
    gap: 5px;
    background: #fff;
    border: 1px solid #CBCBCB;
    border-radius: 5px;
    padding: 4px 8px;
    width: 220px;
    transition: border-color 150ms, box-shadow 150ms;
  }

  .search-wrap:focus-within {
    border-color: #6CB4F7;
    box-shadow: 0 0 0 2.5px rgba(59, 153, 252, 0.3);
  }

  .search-svg {
    color: #999;
    flex-shrink: 0;
  }

  input {
    flex: 1;
    border: none;
    outline: none;
    background: none;
    font-size: 12px;
    font-family: inherit;
    color: #1d1d1f;
    min-width: 0;
  }

  input::placeholder {
    color: #b0b0b0;
  }

  .loader {
    width: 11px;
    height: 11px;
    border: 1.5px solid #e0e0e0;
    border-top-color: #888;
    border-radius: 50%;
    animation: spin 0.5s linear infinite;
    flex-shrink: 0;
  }

  @keyframes spin { to { transform: rotate(360deg); } }

  .col-header {
    display: flex;
    align-items: center;
    padding: 3px 16px 3px 52px;
    background: #F8F8F8;
    border-bottom: 1px solid #E0E0E0;
    font-size: 11px;
    font-weight: 500;
    color: #777;
    user-select: none;
  }

  .col-name { flex: 1; }
  .col-date { width: 100px; text-align: right; padding-right: 12px; }
  .col-match { width: 60px; text-align: right; }

  .results-area {
    flex: 1;
    overflow-y: auto;
    background: #fff;
  }

  .result-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 5px 16px;
    border: none;
    background: none;
    font-family: inherit;
    font-size: 13px;
    color: #1d1d1f;
    cursor: default;
    text-align: left;
  }

  .result-item.even {
    background: #FAFAFA;
  }

  .result-item:hover:not(.selected) {
    background: #F0F0F0;
  }

  .result-item.selected {
    background: #1A73E8;
    color: #fff;
    border-radius: 0;
  }

  .result-item.selected .file-loc,
  .result-item.selected .file-date,
  .result-item.selected .file-score {
    color: rgba(255, 255, 255, 0.75);
  }

  .result-item.selected .file-name {
    color: #fff;
  }

  .result-item.selected .file-svg path:first-child {
    fill: rgba(255, 255, 255, 0.15);
    stroke: rgba(255, 255, 255, 0.4);
  }
  .result-item.selected .file-svg path:last-child {
    fill: rgba(255, 255, 255, 0.1);
    stroke: rgba(255, 255, 255, 0.3);
  }

  .file-icon-wrap {
    position: relative;
    width: 26px;
    height: 32px;
    flex-shrink: 0;
  }

  .file-svg {
    display: block;
  }

  .ext-badge {
    position: absolute;
    bottom: 2px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 6.5px;
    font-weight: 700;
    color: #fff;
    padding: 0.5px 2.5px;
    border-radius: 1.5px;
    line-height: 1.2;
    letter-spacing: 0.3px;
    white-space: nowrap;
  }

  .file-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0px;
  }

  .file-name {
    font-size: 12px;
    font-weight: 400;
    color: #1d1d1f;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.3;
  }

  .file-loc {
    font-size: 10.5px;
    color: #999;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.3;
  }

  .file-date {
    width: 100px;
    text-align: right;
    font-size: 11px;
    color: #999;
    flex-shrink: 0;
    white-space: nowrap;
    padding-right: 12px;
  }

  .file-score {
    width: 60px;
    text-align: right;
    font-size: 11px;
    color: #999;
    flex-shrink: 0;
    font-variant-numeric: tabular-nums;
  }

  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 240px;
    gap: 4px;
    user-select: none;
  }

  .empty-title {
    font-size: 14px;
    font-weight: 500;
    color: #aaa;
  }

  .empty-sub {
    font-size: 12px;
    color: #ccc;
  }

  .statusbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 3px 16px;
    background: #F5F5F5;
    border-top: 1px solid #D4D4D4;
    font-size: 11px;
    color: #999;
    min-height: 22px;
  }

  .status-right {
    color: #bbb;
  }

  .results-area::-webkit-scrollbar {
    width: 8px;
  }
  .results-area::-webkit-scrollbar-track {
    background: transparent;
  }
  .results-area::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.12);
    border-radius: 4px;
    border: 2px solid transparent;
    background-clip: content-box;
  }
  .results-area::-webkit-scrollbar-thumb:hover {
    background: rgba(0, 0, 0, 0.25);
    background-clip: content-box;
  }
</style>
