#!/usr/bin/env bash
# ============================================================================
# FileSense — Development runner
#
# Runs the Python sidecar independently for development and testing.
# Usage:
#   ./dev.sh              # Start the sidecar server
#   ./dev.sh test         # Run the test suite
#   ./dev.sh index        # Trigger a manual full re-index
#   ./dev.sh search "q"   # Quick search from the command line
# ============================================================================

set -euo pipefail
cd "$(dirname "$0")/src-python"

# Activate venv if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

case "${1:-run}" in
    run|start)
        echo "🔍 Starting FileSense sidecar on http://127.0.0.1:9274"
        python main.py
        ;;

    test)
        echo "🧪 Running tests..."
        python -m pytest tests/ -v --tb=short "${@:2}"
        ;;

    search)
        if [ -z "${2:-}" ]; then
            echo "Usage: ./dev.sh search \"your query here\""
            exit 1
        fi
        echo "🔍 Searching: $2"
        curl -s -X POST http://127.0.0.1:9274/api/search \
            -H "Content-Type: application/json" \
            -d "{\"query\": \"$2\", \"top_k\": 10}" | python -m json.tool
        ;;

    status)
        echo "📊 Index status:"
        curl -s http://127.0.0.1:9274/api/status | python -m json.tool
        ;;

    index)
        path="${2:-$HOME/Documents}"
        echo "📁 Re-indexing: $path"
        curl -s -X POST "http://127.0.0.1:9274/api/reindex?path=$(python -c "import urllib.parse; print(urllib.parse.quote('$path'))")" | python -m json.tool
        ;;

    health)
        curl -s http://127.0.0.1:9274/api/health | python -m json.tool
        ;;

    *)
        echo "FileSense Development Helper"
        echo ""
        echo "Commands:"
        echo "  ./dev.sh run          Start the sidecar server"
        echo "  ./dev.sh test         Run the test suite"
        echo "  ./dev.sh search \"q\"   Quick CLI search"
        echo "  ./dev.sh status       Show index status"
        echo "  ./dev.sh index [path] Re-index a directory"
        echo "  ./dev.sh health       Health check"
        ;;
esac
