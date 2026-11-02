from __future__ import annotations

import json
from typing import Any

from ..core.models import WordTiming
from ..core.stage import RunContext, Stage, StageResult
from ..media.ass import build_ass
from .script import load_plan
from .tts import load_tts
from .video import timeline_for


class CaptionsStage(Stage):
    """Karaoke captions placed at each beat's speech start on the edit timeline, plus on-screen title cards."""

    name = "captions"
    requires = ("tts", "video")

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        d = super().inputs(ctx)
        d["honorifics"] = [h.model_dump() for h in ctx.cfg.topic.honorifics]
        d["safe_zone"] = ctx.cfg.global_.safe_zone.model_dump()
        d["video_pacing"] = ctx.cfg.stages.get("video", {})
        if ctx.job.scene_plan_path.exists():
            d["titles"] = [(s.id, s.on_screen_text) for s in load_plan(ctx).scenes]
        return d

    def run(self, ctx: RunContext) -> StageResult:
        cc = ctx.stage_cfg("captions")
        reel, sz = ctx.cfg.global_.reel, ctx.cfg.global_.safe_zone
        plan = load_plan(ctx)
        tts = {a.scene_id: a for a in load_tts(ctx)}
        tl = timeline_for(ctx)
        scene_words: list[tuple[float, list[WordTiming]]] = [(b.speech_start, tts[b.beat_id].words) for b in tl.beats]
        title_seconds = float(getattr(cc, "title_seconds", 2.6))
        titles = []
        beat_of = {b.beat_id: b for b in tl.beats}
        for sc in plan.scenes:
            if sc.on_screen_text:
                b = beat_of[sc.id]
                titles.append((b.start + 0.05, b.start + min(b.duration, title_seconds), sc.on_screen_text))
        ass = build_ass(scene_words, width=reel.width, height=reel.height, style=cc.style.model_dump(),
                        bottom_margin_px=sz.bottom_px, side_margin_px=sz.side_px, words_per_group=cc.words_per_group,
                        pop_in_ms=cc.pop_in_ms, honorifics=[h.model_dump() for h in ctx.cfg.topic.honorifics],
                        uppercase=bool(getattr(cc, "uppercase", False)), titles=titles,
                        title_style=getattr(cc, "title_style", None) or {}, top_margin_px=sz.top_px)
        out_dir = ctx.job.dir("captions")
        (out_dir / "captions.ass").write_text(ass, encoding="utf-8")
        (out_dir / "timeline.json").write_text(json.dumps({
            "total": tl.total,
            "beats": [{"beat_id": b.beat_id, "start": b.start, "speech_start": b.speech_start, "duration": b.duration}
                      for b in tl.beats],
            "shots": [{"shot_id": s.shot_id, "start": s.start, "own": s.own, "overlap": s.overlap,
                       "transition_out": s.transition_out} for s in tl.shots],
            "dropped": tl.dropped}, indent=2), encoding="utf-8")
        return StageResult(artifacts=["08_captions/captions.ass", "08_captions/timeline.json"])
