#!/usr/bin/env bash
# Start one ComfyUI instance per GPU inside tmux (alternative to systemd). Usage: bash scripts/comfy_tmux.sh [COMFY_ROOT]
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMFY_ROOT="${1:-${COMFY_ROOT:-$REPO_DIR/runtime/comfy}}"
N=$(nvidia-smi --list-gpus | wc -l)
for i in $(seq 0 $((N - 1))); do
  tmux kill-session -t "comfy$i" 2>/dev/null || true
  tmux new-session -d -s "comfy$i" "cd $COMFY_ROOT/ComfyUI && PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    .venv/bin/python main.py --listen 127.0.0.1 --port 818$i --cuda-device $i --use-sage-attention --disable-auto-launch \
    --output-directory $COMFY_ROOT/output/$i --temp-directory $COMFY_ROOT/temp/$i 2>&1 | tee -a $COMFY_ROOT/comfy$i.log"
  echo "started tmux session comfy$i on port 818$i (attach: tmux attach -t comfy$i)"
done
