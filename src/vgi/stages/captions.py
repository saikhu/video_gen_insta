from __future__ import annotations

import json
from typing import Any

from ..core.models import WordTiming
from ..core.stage import RunContext, Stage, StageResult
from ..media.ass import build_ass
from .tts import load_tts
from .video import load_clips


def timeline(clips: list[dict[str, Any]], xfade: float) -> list[dict[str, float]]:
    """Absolute start of each segment on the final timeline (segments overlap by xfade)."""
    t, rows = 0.0, []
    for i, c in enumerate(clips):
        rows.append({"scene_id": c["scene_id"], "start": round(t, 3), "seconds": c["seconds"]})
        t += c["seconds"] - xfade
    return rows


class CaptionsStage(Stage):
    name = "captions"
    requires = ("tts", "video")

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        d = super().inputs(ctx)
        d["honorifics"] = [h.model_dump() for h in ctx.cfg.topic.honorifics]
        d["safe_zone"] = ctx.cfg.global_.safe_zone.model_dump()
        return d

    def run(self, ctx: RunContext) -> StageResult:
        cc, vc = ctx.stage_cfg("captions"), ctx.stage_cfg("video")
        reel, sz = ctx.cfg.global_.reel, ctx.cfg.global_.safe_zone
        clips = load_clips(ctx)
        tts = {a.scene_id: a for a in load_tts(ctx)}
        rows = timeline(clips, vc.xfade_seconds)
        scene_words: list[tuple[float, list[WordTiming]]] = []
        for r in rows:
            a = tts[r["scene_id"]]
            scene_words.append((r["start"] + vc.xfade_seconds, a.words))   # narration starts after the lead-in
        ass = build_ass(scene_words, width=reel.width, height=reel.height, style=cc.style.model_dump(),
                        bottom_margin_px=sz.bottom_px, side_margin_px=sz.side_px, words_per_group=cc.words_per_group,
                        pop_in_ms=cc.pop_in_ms, honorifics=[h.model_dump() for h in ctx.cfg.topic.honorifics])
        out_dir = ctx.job.dir("captions")
        (out_dir / "captions.ass").write_text(ass, encoding="utf-8")
        (out_dir / "timeline.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
        return StageResult(artifacts=["08_captions/captions.ass", "08_captions/timeline.json"])
