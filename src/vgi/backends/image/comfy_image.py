"""ComfyUI image backend (Z-Image Turbo / FLUX 3 Klein via API-format workflow templates). Thread-safe: each call
holds one ComfyUI instance from the pool, so the keyframes stage can render on every GPU at once."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..comfy_client import ComfyError, EndpointPool, fill_workflow


class ComfyImageBackend:
    name = "comfy"

    def __init__(self, endpoints: list[str], workflows_dir: Path, workflow: str, timeout_s: int = 600):
        self.pool = EndpointPool(endpoints)
        self.template_path = Path(workflows_dir) / f"{workflow}.json"
        self.timeout_s = timeout_s

    def generate(self, prompt: str, negative: str, width: int, height: int, seed: int, out: Path, *,
                 steps: int = 8, guidance: float = 2.0, prefix: str = "vgi", **_) -> Path:
        if not self.template_path.exists():
            raise ComfyError(f"workflow template missing: {self.template_path}")
        tpl: dict[str, Any] = json.loads(self.template_path.read_text(encoding="utf-8"))
        wf = fill_workflow(tpl, {"prompt": prompt, "negative": negative, "width": width, "height": height,
                                 "seed": seed, "steps": steps, "guidance": guidance, "prefix": prefix})
        client = self.pool.acquire()
        try:
            pid = client.queue_prompt(wf)
            hist = client.wait(pid, self.timeout_s)
            files = [f for f in client.outputs(hist) if f["filename"].lower().endswith((".png", ".jpg", ".webp"))]
            if not files:
                raise ComfyError("workflow produced no image")
            client.download(files[0], out)
            return out
        finally:
            self.pool.release(client)
