"""ComfyUI video backend (LTX-2.5 / Wan 2.2 via API-format workflow templates)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..comfy_client import ComfyError, EndpointPool, fill_workflow


class ComfyVideoBackend:
    name = "comfy"

    def __init__(self, endpoints: list[str], workflows_dir: Path, workflow_i2v: str, workflow_flf2v: str,
                 timeout_s: int, log=None, retries: int = 1):
        self.pool = EndpointPool(endpoints)
        self.workflows_dir = Path(workflows_dir)
        self.workflow_i2v, self.workflow_flf2v = workflow_i2v, workflow_flf2v
        self.timeout_s = timeout_s
        self.log = log
        self.retries = max(0, retries)

    def _template(self, name: str) -> dict[str, Any]:
        p = self.workflows_dir / f"{name}.json"
        if not p.exists():
            raise ComfyError(f"workflow template missing: {p} (export it from ComfyUI in API format)")
        return json.loads(p.read_text(encoding="utf-8"))

    def generate(self, keyframe: Path, out: Path, seconds: float, seed: int, *, prompt: str, negative: str,
                 frames: int, width: int, height: int, steps: int, fps: int, prefix: str,
                 last_frame: Path | None = None, upscale: int = 1, **_) -> Path:
        """One attempt per endpoint acquisition; on failure, release, wait briefly, and retry up to self.retries."""
        import time

        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return self._generate_once(keyframe, out, seed, prompt=prompt, negative=negative, frames=frames, width=width,
                                           height=height, steps=steps, fps=fps, prefix=prefix, last_frame=last_frame,
                                           upscale=upscale)
            except ComfyError as e:
                last_err = e
                if attempt < self.retries:
                    if self.log:
                        self.log.warn(f"attempt {attempt + 1} failed ({str(e)[:120]}); retrying", prefix=prefix)
                    time.sleep(5)
        raise last_err  # type: ignore[misc]

    def _generate_once(self, keyframe: Path, out: Path, seed: int, *, prompt: str, negative: str, frames: int, width: int,
                       height: int, steps: int, fps: int, prefix: str, last_frame: Path | None, upscale: int) -> Path:
        client = self.pool.acquire()
        try:
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
                self.log.debug("queued", endpoint=client.endpoint, prompt_id=prompt_id, frames=frames, prefix=prefix)
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
        finally:
            self.pool.release(client)

    @property
    def workers(self) -> int:
        return max(1, self.pool.size)
