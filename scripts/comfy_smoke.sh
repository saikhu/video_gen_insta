#!/usr/bin/env bash
# Smoke test every ComfyUI endpoint from configs/env/linux_2x3090.yaml: health, VRAM, queue, and a workflow dry-validate.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
for port in 8188 8189; do
  if curl -sf "http://127.0.0.1:$port/system_stats" >/dev/null; then
    uv run python - "$port" <<'PY'
import sys
from vgi.backends.comfy_client import ComfyClient
c = ComfyClient(f"http://127.0.0.1:{sys.argv[1]}")
st = c.system_stats(); dev = st["devices"][0]
print(f"{c.endpoint}: {dev['name']}  vram_free={dev['vram_free']/2**30:.1f} GB  queue={c.queue_depth()}  comfy={st['system'].get('comfyui_version','?')}")
PY
  else
    echo "http://127.0.0.1:$port: DOWN"
  fi
done
uv run vgi doctor --env linux_2x3090
