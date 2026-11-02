#!/usr/bin/env bash
# Run the repo-local Ollama (runtime/ollama) with models stored in models/ollama. Used by systemd (vgi-ollama)
# and for manual starts. A system-wide `ollama` on PATH is used instead when runtime/ollama is absent.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$REPO_DIR/runtime/ollama/bin/ollama"
[ -x "$BIN" ] || BIN="$(command -v ollama)"
export OLLAMA_MODELS="${OLLAMA_MODELS:-$REPO_DIR/models/ollama}"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:-0}"      # unload after each request: ComfyUI needs the VRAM back
mkdir -p "$OLLAMA_MODELS"
exec "$BIN" serve
