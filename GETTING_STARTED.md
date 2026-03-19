# Getting Started with FileSense

This guide walks you through setting up FileSense for development,
from zero to a working semantic search on your Mac.

## Prerequisites

You'll need four tools installed. Here's the fastest way to get each one.

### 1. Rust toolchain

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
rustc --version  # Should print 1.75+
```

### 2. Node.js 20+ and pnpm

```bash
# Using Homebrew
brew install node
npm install -g pnpm

# Or using nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
nvm install 20
npm install -g pnpm
```

### 3. Python 3.11+ and uv

```bash
# Python (likely already installed on macOS)
python3 --version  # Should print 3.11+

# uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 4. Tauri CLI

```bash
pnpm add -g @tauri-apps/cli
```

---

## Setup

### Clone and install frontend dependencies

```bash
cd filesense
pnpm install
```

### Set up the Python environment

```bash
cd src-python
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Install test dependencies
uv pip install pytest pytest-asyncio coverage
```

### Download the embedding model (one-time, ~80MB)

```bash
python -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
print(f'Model loaded. Dimensions: {model.get_sentence_embedding_dimension()}')
"
```

This downloads the model to `~/.cache/torch/sentence_transformers/`.

---

## Development Workflow

### Option A: Full-stack (Tauri + Svelte + Python)

```bash
# Terminal 1: Start the Python sidecar
cd src-python && source .venv/bin/activate
python main.py

# Terminal 2: Start Tauri dev mode
cd filesense
pnpm tauri dev
```

This gives you hot-reload on the frontend and the search overlay
accessible via Cmd+Shift+Space.

### Option B: Python backend only

```bash
cd src-python && source .venv/bin/activate
./dev.sh run
```

Then test with curl:

```bash
# Health check
curl http://127.0.0.1:9274/api/health

# Check index status
curl http://127.0.0.1:9274/api/status

# Search
curl -X POST http://127.0.0.1:9274/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning notes", "top_k": 10}'
```

### Option C: Quick CLI search

```bash
./dev.sh search "quarterly budget report"
./dev.sh status
```

---

## Running Tests

```bash
cd src-python
source .venv/bin/activate

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_chunker.py -v

# Run with coverage
coverage run -m pytest tests/
coverage report
coverage html  # Opens detailed HTML report
```

### What the tests cover

| Test file | What it validates |
|---|---|
| `test_chunker.py` | Text splitting, overlap, edge cases, Unicode |
| `test_extractor.py` | PDF/docx/csv/txt extraction, encoding handling |
| `test_embeddings.py` | Model loading, vector dimensions, semantic similarity |
| `test_optimizations.py` | LRU cache, priority queue, batch scheduler |
| `test_integration.py` | Full pipeline: index files → search → verify ranking |

The integration test (`test_integration.py`) is the most important one.
It creates real temporary files, indexes them, and verifies that semantic
search returns the right files for natural language queries.

---

## Configuration

All settings live in `src-python/app/core/config.py` and can be
overridden with environment variables prefixed with `FILESENSE_`.

### Key settings to customize

**Watch directories** — By default, FileSense indexes Documents, Desktop,
and Downloads. Add more in settings or via environment:

```bash
export FILESENSE_WATCH_DIRECTORIES='["/Users/you/Projects", "/Users/you/Notes"]'
```

**Embedding provider** — Switch to OpenAI for higher quality:

```bash
export FILESENSE_EMBEDDING_PROVIDER=openai
export FILESENSE_OPENAI_API_KEY=sk-...
```

Note: switching providers requires a full re-index.

**Chunk size** — The default 500 tokens works well for most documents.
For code files, you might want smaller chunks (300). For long-form
writing, larger chunks (800) can capture more context.

---

## Architecture Quick Reference

```
User types query
  → Svelte UI sends POST /api/search
  → FastAPI embeds the query text
  → LanceDB cosine similarity search
  → Re-ranking (filename match, recency, multi-chunk)
  → Results returned to UI in <100ms

File changes detected
  → watchdog FSEvents handler
  → Debounce queue (2s)
  → Extract text (PyMuPDF / python-docx / etc.)
  → Chunk into ~500 token windows
  → Embed with sentence-transformers
  → Upsert into LanceDB + update SQLite metadata
```

---

## Performance Expectations

Benchmarked on M1 MacBook Pro (16GB RAM):

| Operation | Speed |
|---|---|
| Initial index (10k files) | ~4 minutes |
| Single file re-index | ~200ms |
| Search latency (100k vectors) | ~50ms |
| Embedding throughput (local) | ~500 chunks/sec |
| Memory usage (idle) | ~250MB |
| Memory usage (indexing) | ~600MB |
| Disk usage (100k vectors) | ~300MB |

---

## Common Issues

**"Model download is slow"** — The first run downloads ~80MB. After that
it's cached. If you're behind a proxy, set `HF_ENDPOINT` or download
the model manually from HuggingFace.

**"Permission denied reading files"** — macOS requires explicit
permission for file access. Go to System Settings → Privacy & Security →
Files and Folders, and grant FileSense access. Or run with Full Disk
Access for development.

**"Port 9274 already in use"** — Another instance is running. Kill it:
`lsof -ti:9274 | xargs kill -9`

**"Search returns weird results"** — Check that the file was actually
indexed: `./dev.sh status`. If the file type isn't in `supported_extensions`,
add it in config.py. Also check chunk_size — very large files might
need smaller chunks for precise matching.

**"High memory during indexing"** — The embedding model uses ~250MB.
During batch indexing, the queue can grow. Reduce `batch_size` in
config.py or limit `watch_directories` to start.

---

## Next Steps

Once you have the basic search working, here are the highest-impact
improvements to build next:

1. **File preview panel** — Show a rendered preview of the selected file
   (PDF thumbnail, Markdown rendered, code with syntax highlighting).

2. **Fuzzy filename fallback** — If semantic search returns no results,
   fall back to fuzzy filename matching so the app is always useful.

3. **Search filters UI** — Let users filter by file type, date range,
   or directory using keyboard shortcuts (e.g., `type:pdf budget`).

4. **Incremental re-ranking** — Track which results users actually open
   and boost those files in future searches (lightweight learning-to-rank).

5. **Multi-modal indexing** — Use macOS Vision framework to OCR images
   and screenshots, making them searchable too.

6. **Sync across devices** — Encrypt and sync the vector index via
   iCloud Drive or Cloudflare R2 for multi-Mac setups.
