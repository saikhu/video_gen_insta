from __future__ import annotations

import json

from ..core.stage import RunContext, Stage, StageResult
from ..media.ffmpeg import silence_wav


class MusicStage(Stage):
    name = "music"
    requires = ("tts",)

    def run(self, ctx: RunContext) -> StageResult:
        mc = ctx.stage_cfg("music")
        policy = ctx.cfg.topic.music_policy
        out_dir = ctx.job.dir("music")
        info = {"engine": mc.engine, "policy": policy, "bed": None}
        log = ctx.log.for_stage("music")
        engine = "none" if policy in ("none", "native_only") else mc.engine
        if engine == "stub":
            silence_wav(out_dir / "bed.wav", 90, ctx.cfg.global_.reel.audio_sample_rate)
            info["bed"] = "07_music/bed.wav"
        elif engine == "ace_step":
            log.warn("ACE-Step music generation is a v1.5 feature; no bed will be mixed")
        elif engine != "none":
            log.warn(f"unknown music engine {engine!r}; no bed")
        (out_dir / "music.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        return StageResult(artifacts=["07_music/music.json"] + ([info["bed"]] if info["bed"] else []), backend=engine)
