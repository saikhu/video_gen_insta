"""ComfyUI video backend (LTX-2.5 / Wan 2.2 via API-format workflow templates)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..comfy_client import ComfyError, EndpointPool, fill_workflow


class ComfyVideoBackend:
    name = "comfy"

    def __init__(self, endpoints: list[str], workflows_dir: Path, workflow_i2v: str, workflow_flf2v: str,
                 timeout_s: int, log=None):
        self.pool = EndpointPool(endpoints)
        self.workflows_dir = Path(workflows_dir)
        self.workflow_i2v, self.workflow_flf2v = workflow_i2v, workflow_flf2v
        self.timeout_s = timeout_s
        self.log = log

    def _template(self, name: str) -> dict[str, Any]:
        p = self.workflows_dir / f"{name}.json"
        if not p.exists():
            raise ComfyError(f"workflow template missing: {p} (export it from ComfyUI in API format)")
        return json.loads(p.read_text(encoding="utf-8"))

    def generate(self, keyframe: Path, out: Path, seconds: float, seed: int, *, prompt: str, negative: str,
                 frames: int, width: int, height: int, steps: int, fps: int, prefix: str,
                 last_frame: Path | None = None, upscale: int = 1, **_) -> Path:
        client = self.pool.next()
        image_ref = client.upload_image(keyframe)
        values = {"image": image_ref, "prompt": prompt, "negative": negative, "seed": seed, "frames": frames,
                  "width": width, "height": height, "final_width": width * upscale, "final_height": height * upscale,
                  "steps": steps, "fps": fps, "prefix": prefix}
        name = self.workflow_i2v
        if last_frame is not None:
            values["last_image"] = client.upload_image(last_frame)
            name = self.workflow_flf2v
        wf = fill_workflow(self._template(name), values)
        prompt_id = client.queue_prompt(wf)
        if self.log:
            self.log.info("queued", endpoint=client.endpoint, prompt_id=prompt_id, frames=frames)
        try:
            hist = client.wait(prompt_id, self.timeout_s)
        except ComfyError as e:
            if "timeout" in str(e):
                client.interrupt()
            if "memory" in str(e).lower() or "oom" in str(e).lower():
                client.free()
            raise
        files = [f for f in client.outputs(hist) if f["filename"].lower().endswith((".mp4", ".webm", ".mov"))]
        if not files:
            raise ComfyError("workflow produced no video file")
        out.parent.mkdir(parents=True, exist_ok=True)
        client.download(files[0], out)
        out.with_suffix(".prompt_id").write_text(prompt_id)
        return out
