from __future__ import annotations

import json
from typing import Any

from ..backends.registry import tts_backend
from ..core.models import SceneAudio
from ..core.stage import RunContext, Stage, StageResult
from .script import load_plan


class TtsStage(Stage):
    name = "tts"
    requires = ("script",)

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        d = {"cfg": ctx.cfg.stages.get("tts", {}), "voice": ctx.cfg.voice, "lexicon": ctx.cfg.lexicon, "dry_run": ctx.dry_run,
             "wps": ctx.cfg.topic.narration.get("words_per_second")}
        if ctx.job.scene_plan_path.exists():
            d["narration"] = [(s.id, s.narration_text) for s in load_plan(ctx).scenes]
        return d

    def run(self, ctx: RunContext) -> StageResult:
        tc = ctx.stage_cfg("tts")
        plan = load_plan(ctx)
        backend = tts_backend(ctx)
        out_dir = ctx.job.dir("tts")
        audios: list[SceneAudio] = []
        for s in plan.scenes:
            wav = out_dir / f"scene_{s.id:02d}.wav"
            dur, words = backend.synthesize(s.narration_text, wav, sample_rate=tc.sample_rate)
            audios.append(SceneAudio(scene_id=s.id, wav=f"05_tts/{wav.name}", duration=round(dur, 3), words=words))
        (out_dir / "tts.json").write_text(json.dumps([a.model_dump() for a in audios], indent=2), encoding="utf-8")
        total = sum(a.duration for a in audios)
        ctx.log.for_stage("tts").info(f"{len(audios)} scenes, {total:.1f}s narration", backend=backend.name)
        return StageResult(artifacts=["05_tts/tts.json", *[a.wav for a in audios]], backend=backend.name)


def load_tts(ctx: RunContext) -> list[SceneAudio]:
    raw = json.loads((ctx.job.dir("tts") / "tts.json").read_text(encoding="utf-8"))
    return [SceneAudio.model_validate(r) for r in raw]
