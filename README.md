# FileSense — AI-Powered Semantic File Search for macOS

> Find files by *meaning*, not just by name. FileSense vectorizes your entire file system
> and uses semantic search to surface the files you actually want.

## Architecture

```
┌─────────────────────────────────────────────┐
│  Tauri Shell (.dmg)                         │
│  ┌──────────────────────────────────────┐   │
│  │  Svelte + TypeScript UI              │   │
│  │  • Spotlight-style overlay           │   │
│  │  • Results panel with previews       │   │
│  │  • Settings & indexing status         │   │
│  └──────────────┬───────────────────────┘   │
│                 IPC (JSON-RPC)               │
│  ┌──────────────┴───────────────────────┐   │
│  │  Python Sidecar (FastAPI + Uvicorn)  │   │
│  │  • Search pipeline                   │   │
│  │  • Indexing pipeline                 │   │
│  │  • Embedding provider abstraction    │   │
│  └──────────────┬───────────────────────┘   │
│  ┌──────────────┴───────────────────────┐   │
│  │  Storage                             │   │
│  │  • LanceDB (vectors)                 │   │
│  │  • SQLite (metadata + config)        │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| App shell | Tauri 2.x | Tiny binary, native macOS feel, sidecar support |
| Frontend | Svelte 5 + TypeScript | Minimal bundle, fast reactivity, no runtime |
| Backend | Python 3.11+ / FastAPI | ML ecosystem, your comfort zone |
| Embeddings (local) | sentence-transformers / all-MiniLM-L6-v2 | 384-dim, ~80MB, CPU-fast |
| Embeddings (cloud) | OpenAI text-embedding-3-small | 1536-dim, $0.02/M tokens |
| Vector DB | LanceDB | Embedded, zero-config, Rust-fast |
| Metadata DB | SQLite (aiosqlite) | Embedded, battle-tested |
| File watching | watchdog (FSEvents backend) | Efficient macOS integration |
| Text extraction | PyMuPDF, python-docx, python-pptx | Covers 90%+ of file types |
| Packaging | PyInstaller + Tauri bundler | Single .dmg distribution |
| Auto-update | Sparkle (tauri-plugin-updater) | Seamless OTA updates |

## Getting Started

### Prerequisites
- macOS 13+ (Ventura or later)
- Node.js 20+ and pnpm
- Python 3.11+ and uv (or pip)
- Rust toolchain (for Tauri)

### Setup

```bash
# Clone and install frontend deps
cd filesense
pnpm install

# Set up Python environment
cd src-python
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Download the local embedding model (first run only)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Run in development
cd ..
pnpm tauri dev
```

## Project Structure

See each directory's README for detailed documentation.
