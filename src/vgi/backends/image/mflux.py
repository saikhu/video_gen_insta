"""mflux (MLX) image backend for Apple Silicon. Runs the per-model `mflux-generate-*` CLI as a subprocess.

Verified 2026-11-02 with mflux's `mflux-generate-z-image-turbo` (flags: --prompt --negative-prompt --seed --width
--height --steps --guidance -q --output). Other models map to their own entry points below.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

COMMANDS = {
    "z_image_turbo": ("mflux-generate-z-image-turbo", False),   # (command, accepts --guidance)
    "z_image": ("mflux-generate-z-image", True),
    "qwen_image": ("mflux-generate-qwen", True),
    "flux2": ("mflux-generate-flux2", True),
    "flux3_klein": ("mflux-generate-flux3-klein", True),         # unverified entry point; check `ls .venv/bin | grep mflux`
}


_MODEL_CACHE: dict[tuple[str, int | None], object] = {}


def _settle_output(out: Path) -> Path:
    """mflux appends _N when the path exists; move such a file to the requested name."""
    if out.exists():
        return out
    cands = sorted(out.parent.glob(f"{out.stem}_[0-9]*{out.suffix}"), key=lambda p: p.stat().st_mtime)
    if not cands:
        raise RuntimeError(f"mflux produced no file at {out}")
    cands[-1].replace(out)
    return out


class MfluxImageBackend:
    name = "mflux"

    def __init__(self, model: str = "z_image_turbo", quantize: int | None = 8, command: str | None = None,
                 venv_bin: Path | None = None):
        self.model = model
        self.quantize = quantize
        cmd, self.supports_guidance = COMMANDS.get(model, (command or "mflux-generate", True))
        self.command = command or cmd
        self.venv_bin = venv_bin

    def _resolve(self) -> str | None:
        if self.venv_bin and (self.venv_bin / self.command).exists():
            return str(self.venv_bin / self.command)
        return shutil.which(self.command)

    def available(self) -> bool:
        return self._resolve() is not None

    def generate(self, prompt: str, negative: str, width: int, height: int, seed: int, out: Path, *,
                 steps: int = 8, guidance: float = 2.0, **_) -> Path:
        if self.model == "z_image_turbo":
            try:
                return self._generate_inprocess(prompt, width, height, seed, out, steps)
            except ImportError:
                pass  # mflux not importable in this interpreter → CLI path below
        return self._generate_cli(prompt, negative, width, height, seed, out, steps=steps, guidance=guidance)

    def _generate_inprocess(self, prompt: str, width: int, height: int, seed: int, out: Path, steps: int) -> Path:
        """Keep the model resident across scenes (loading it is the slow part). Z-Image Turbo: no CFG, no negative."""
        from mflux.models.z_image.variants.z_image import ZImage

        key = (self.model, self.quantize)
        model = _MODEL_CACHE.get(key)
        if model is None:
            model = ZImage(quantize=self.quantize)
            _MODEL_CACHE[key] = model
        image = model.generate_image(seed=seed, prompt=prompt, num_inference_steps=steps, height=height, width=width)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.unlink(missing_ok=True)  # mflux never overwrites; it would write <name>_1.png instead
        image.save(path=str(out), export_json_metadata=False)
        return _settle_output(out)

    def _generate_cli(self, prompt: str, negative: str, width: int, height: int, seed: int, out: Path, *,
                      steps: int = 8, guidance: float = 2.0) -> Path:
        exe = self._resolve()
        if not exe:
            raise RuntimeError(f"{self.command} not found; install with: uv sync --extra mac")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.unlink(missing_ok=True)  # mflux never overwrites; it would write <name>_1.png instead
        cmd = [exe, "--prompt", prompt, "--width", str(width), "--height", str(height), "--steps", str(steps),
               "--seed", str(seed), "--output", str(out), "--no-metadata"]
        if negative:
            cmd += ["--negative-prompt", negative]
        if self.quantize:
            cmd += ["-q", str(self.quantize)]
        if guidance and self.supports_guidance:
            cmd += ["--guidance", str(guidance)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"mflux failed ({proc.returncode}): {proc.stderr[-800:]}")
        return _settle_output(out)
