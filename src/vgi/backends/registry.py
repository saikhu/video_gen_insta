"""Backend selection from config + environment + dry-run flag."""
from __future__ import annotations

from pathlib import Path

from ..core.stage import RunContext
from .stub import StubImageBackend, StubTTSBackend


def image_backend(ctx: RunContext):
    kf = ctx.stage_cfg("keyframes")
    if ctx.dry_run or kf.backend == "stub":
        return StubImageBackend()
    if kf.backend == "mflux":
        from .image.mflux import MfluxImageBackend

        import sys

        return MfluxImageBackend(model=kf.model, quantize=getattr(kf, "quantize", 8),
                                 command=getattr(kf, "mflux_command", None), venv_bin=Path(sys.executable).parent)
    if kf.backend in ("comfy", "remote_comfy"):
        from .image.comfy_image import ComfyImageBackend

        return ComfyImageBackend(ctx.cfg.env.comfy.endpoints, ctx.root / "comfy" / "workflows", kf.workflow)
    raise ValueError(f"unknown keyframes backend {kf.backend!r}")


def video_backend(ctx: RunContext):
    """Returns (primary, fallback). Primary may be None when only Ken Burns applies."""
    vc = ctx.stage_cfg("video")
    reel = ctx.cfg.global_.reel
    kb = vc.ken_burns
    fallback = __import__("vgi.backends.video.ken_burns", fromlist=["KenBurnsBackend"]).KenBurnsBackend(
        reel.fps, reel.width, reel.height, kb.zoom_start, kb.zoom_end, kb.pre_scale)
    if ctx.dry_run or vc.backend in ("stub", "ken_burns"):
        return None, fallback
    if vc.backend in ("comfy", "remote_comfy"):
        endpoints = ctx.cfg.env.comfy.endpoints
        if not endpoints:
            ctx.log.for_stage("video").warn("no ComfyUI endpoint configured; using ken_burns fallback")
            return None, fallback
        from .video.comfy_video import ComfyVideoBackend

        return ComfyVideoBackend(endpoints, ctx.root / "comfy" / "workflows", vc.workflow_i2v, vc.workflow_flf2v,
                                 vc.timeout_seconds, log=ctx.log.for_stage("video"), retries=vc.retries), fallback
    raise ValueError(f"unknown video backend {vc.backend!r}")


def tts_backend(ctx: RunContext):
    tc = ctx.stage_cfg("tts")
    wps = float(ctx.cfg.topic.narration.get("words_per_second", 2.5))
    if ctx.dry_run or tc.engine == "stub":
        return StubTTSBackend(words_per_second=wps, sample_rate=tc.sample_rate)
    if tc.engine == "kokoro":
        from .tts.kokoro import KokoroTTSBackend

        v = (ctx.cfg.voice or {}).get("kokoro", {})
        return KokoroTTSBackend(voice=v.get("voice", "bm_george"), lang_code=v.get("lang_code", "b"), speed=tc.speed,
                                device=tc.device, lexicon=ctx.cfg.lexicon)
    raise ValueError(f"TTS engine {tc.engine!r} not implemented in v1 (kokoro | stub)")


def workflows_dir(root: Path) -> Path:
    return root / "comfy" / "workflows"
