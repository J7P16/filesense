/**
 * FileSense API client.
 *
 * Typed wrapper around the Python sidecar HTTP API.
 * All calls go to 127.0.0.1:9274 — the local-only FastAPI server.
 */

const API_BASE = "http://127.0.0.1:9274/api";

// --- Types ---

export interface SearchResult {
  file_path: string;
  file_name: string;
  file_type: string;
  snippet: string;
  similarity: number;
  final_score: number;
  last_modified: number;
  chunk_count: number;
}

export interface SearchResponse {
  results: SearchResult[];
  query: string;
  elapsed_ms: number;
}

export interface IndexStatus {
  total_files: number;
  indexed_files: number;
  total_chunks: number;
  failed_files: number;
  queue_size: number;
  pending_debounce: number;
  is_running: boolean;
  provider: string;
}

export interface ReindexResponse {
  status: string;
  reindexed?: number;
  message?: string;
}

// --- API calls ---

export async function search(
  query: string,
  topK: number = 20,
  fileType?: string
): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      top_k: topK,
      file_type: fileType ?? null,
    }),
  });

  if (!res.ok) {
    throw new Error(`Search failed: ${res.status} ${res.statusText}`);
  }

  return res.json();
}

export async function getStatus(): Promise<IndexStatus> {
  const res = await fetch(`${API_BASE}/status`);
  if (!res.ok) {
    throw new Error(`Status check failed: ${res.status}`);
  }
  return res.json();
}

export async function reindex(path: string): Promise<ReindexResponse> {
  const res = await fetch(`${API_BASE}/reindex?path=${encodeURIComponent(path)}`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error(`Reindex failed: ${res.status}`);
  }
  return res.json();
}

export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, {
      signal: AbortSignal.timeout(2000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Wait for the sidecar to become available.
 * Polls the health endpoint every 500ms up to maxWaitMs.
 */
export async function waitForSidecar(maxWaitMs: number = 15000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    if (await healthCheck()) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}
