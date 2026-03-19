#!/usr/bin/env bash
# ============================================================================
# FileSense — Build & Distribution Script for macOS
#
# Builds the complete app: Python sidecar → Tauri shell → signed .dmg
#
# Usage:
#   ./build.sh dev        # Development build (no signing)
#   ./build.sh release    # Release build with notarization
#   ./build.sh sidecar    # Build only the Python sidecar binary
#   ./build.sh clean      # Clean all build artifacts
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[build]${NC} $1"; }
ok()   { echo -e "${GREEN}[  ok ]${NC} $1"; }
warn() { echo -e "${YELLOW}[ warn]${NC} $1"; }
err()  { echo -e "${RED}[error]${NC} $1"; exit 1; }

# ============================================================================
# Step 1: Build the Python sidecar into a standalone binary
# ============================================================================
build_sidecar() {
    log "Building Python sidecar with PyInstaller..."

    cd src-python

    # Activate venv
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    else
        err "Python venv not found. Run: cd src-python && uv venv && uv pip install -r requirements.txt"
    fi

    # Install PyInstaller if missing
    pip show pyinstaller &>/dev/null || pip install pyinstaller --break-system-packages

    # Build standalone binary
    pyinstaller \
        --name filesense-python \
        --onefile \
        --noconfirm \
        --clean \
        --hidden-import=tiktoken_ext.openai_public \
        --hidden-import=tiktoken_ext \
        --collect-data sentence_transformers \
        --collect-data tokenizers \
        main.py

    # Copy binary to Tauri's sidecar location
    mkdir -p "$SCRIPT_DIR/src-tauri/binaries"

    # Determine the target triple
    ARCH=$(uname -m)
    if [ "$ARCH" = "arm64" ]; then
        TARGET="aarch64-apple-darwin"
    else
        TARGET="x86_64-apple-darwin"
    fi

    cp dist/filesense-python "$SCRIPT_DIR/src-tauri/binaries/filesense-python-$TARGET"
    ok "Sidecar built: src-tauri/binaries/filesense-python-$TARGET"

    cd "$SCRIPT_DIR"
}

# ============================================================================
# Step 2: Build the Svelte frontend
# ============================================================================
build_frontend() {
    log "Building Svelte frontend..."
    pnpm install
    pnpm build
    ok "Frontend built to dist/"
}

# ============================================================================
# Step 3: Build the Tauri app
# ============================================================================
build_tauri_dev() {
    log "Building Tauri app (development)..."
    pnpm tauri build --debug
    ok "Dev build complete"
}

build_tauri_release() {
    log "Building Tauri app (release)..."
    pnpm tauri build
    ok "Release build complete"

    # Find the output .dmg
    DMG=$(find src-tauri/target/release/bundle/dmg -name "*.dmg" 2>/dev/null | head -1)
    if [ -n "$DMG" ]; then
        ok "DMG: $DMG"
    fi
}

# ============================================================================
# Step 4: Code signing and notarization (release only)
# ============================================================================
sign_and_notarize() {
    log "Signing and notarizing..."

    APP=$(find src-tauri/target/release/bundle/macos -name "*.app" 2>/dev/null | head -1)
    if [ -z "$APP" ]; then
        err "No .app bundle found"
    fi

    # Sign with entitlements
    if [ -n "${APPLE_SIGNING_IDENTITY:-}" ]; then
        codesign --force --deep --options runtime \
            --entitlements resources/entitlements.plist \
            --sign "$APPLE_SIGNING_IDENTITY" \
            "$APP"
        ok "App signed"

        # Notarize
        if [ -n "${APPLE_ID:-}" ] && [ -n "${APPLE_TEAM_ID:-}" ]; then
            DMG=$(find src-tauri/target/release/bundle/dmg -name "*.dmg" | head -1)
            xcrun notarytool submit "$DMG" \
                --apple-id "$APPLE_ID" \
                --team-id "$APPLE_TEAM_ID" \
                --password "$APPLE_APP_PASSWORD" \
                --wait
            xcrun stapler staple "$DMG"
            ok "App notarized and stapled"
        else
            warn "APPLE_ID / APPLE_TEAM_ID not set — skipping notarization"
        fi
    else
        warn "APPLE_SIGNING_IDENTITY not set — skipping code signing"
        warn "Set it to your Developer ID certificate name for distribution"
    fi
}

# ============================================================================
# Clean
# ============================================================================
clean() {
    log "Cleaning build artifacts..."
    rm -rf src-python/dist src-python/build src-python/*.spec
    rm -rf src-tauri/target
    rm -rf src-tauri/binaries
    rm -rf dist .svelte-kit
    rm -rf node_modules/.vite
    ok "Clean complete"
}

# ============================================================================
# Main
# ============================================================================
case "${1:-dev}" in
    dev)
        build_sidecar
        build_frontend
        build_tauri_dev
        ;;

    release)
        build_sidecar
        build_frontend
        build_tauri_release
        sign_and_notarize
        ;;

    sidecar)
        build_sidecar
        ;;

    frontend)
        build_frontend
        ;;

    clean)
        clean
        ;;

    *)
        echo "FileSense Build Script"
        echo ""
        echo "Usage: ./build.sh [command]"
        echo ""
        echo "Commands:"
        echo "  dev       Development build (default)"
        echo "  release   Release build with signing + notarization"
        echo "  sidecar   Build only the Python sidecar"
        echo "  frontend  Build only the Svelte frontend"
        echo "  clean     Remove all build artifacts"
        echo ""
        echo "Environment variables for release builds:"
        echo "  APPLE_SIGNING_IDENTITY  Developer ID certificate name"
        echo "  APPLE_ID                Apple ID email"
        echo "  APPLE_TEAM_ID           Apple Developer Team ID"
        echo "  APPLE_APP_PASSWORD      App-specific password for notarization"
        ;;
esac
