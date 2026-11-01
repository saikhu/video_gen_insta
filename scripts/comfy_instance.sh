#!/usr/bin/env bash
# Launch ComfyUI instance N on GPU N, port 8188+N. Used by systemd (comfy@N) and scripts/comfy_tmux.sh.
# Usage: scripts/comfy_instance.sh <N> [COMFY_ROOT]
set -euo pipefail
N="${1:?instance index}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMFY_ROOT="${2:-${COMFY_ROOT:-$REPO_DIR/runtime/comfy}}"
PORT=$((8188 + N))
EXTRA_ARGS="${COMFY_EXTRA_ARGS:---use-sage-attention}"
mkdir -p "$COMFY_ROOT/output/$N" "$COMFY_ROOT/temp/$N"
cd "$COMFY_ROOT/ComfyUI"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
exec .venv/bin/python main.py --listen 127.0.0.1 --port "$PORT" --cuda-device "$N" $EXTRA_ARGS --disable-auto-launch \
  --output-directory "$COMFY_ROOT/output/$N" --temp-directory "$COMFY_ROOT/temp/$N"
