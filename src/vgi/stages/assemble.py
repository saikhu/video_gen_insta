from __future__ import annotations

import json
from typing import Any

from ..core.stage import RunContext, Stage, StageResult
from ..media.ffmpeg import concat_xfade, finalize, has_libass, loudnorm_measure, make_segment
from .tts import load_tts
from .video import load_clips


class AssembleStage(Stage):
    name = "assemble"
    requires = ("video", "tts", "captions", "music")

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        d = super().inputs(ctx)
        d["reel"] = ctx.cfg.global_.reel.model_dump()
        return d

    def run(self, ctx: RunContext) -> StageResult:
        ac, vc, mc = ctx.stage_cfg("assemble"), ctx.stage_cfg("video"), ctx.stage_cfg("music")
        reel = ctx.cfg.global_.reel
        clips = load_clips(ctx)
        tts = {a.scene_id: a for a in load_tts(ctx)}
        music = json.loads((ctx.job.dir("music") / "music.json").read_text(encoding="utf-8"))
        bed = ctx.job.path / music["bed"] if music.get("bed") else None
        out_dir = ctx.job.dir("assemble")
        work = out_dir / "work"
        work.mkdir(exist_ok=True)
        segs, durs = [], []
        for c in clips:
            seg = work / f"seg_{c['scene_id']:02d}.mp4"
            make_segment(ctx.job.path / c["path"], ctx.job.path / tts[c["scene_id"]].wav, seg, c["seconds"], vc.xfade_seconds,
                         reel.width, reel.height, reel.fps, reel.audio_sample_rate, bed=bed, bed_gain_db=mc.bed_gain_db,
                         duck_db=mc.duck_db, use_clip_audio=vc.native_audio)
            segs.append(seg)
            durs.append(float(c["seconds"]))
        raw = work / "assembled_raw.mp4"
        total = concat_xfade(segs, durs, raw, vc.xfade_seconds, ac.transition, reel.fps, reel.audio_sample_rate)
        measured = loudnorm_measure(raw, reel.loudness_lufs, reel.true_peak_dbtp, ac.lra) if ac.loudnorm_two_pass else None
        final = out_dir / "final.mp4"
        notes = []
        if not has_libass():
            notes.append("captions NOT burned in: ffmpeg lacks libass (install ffmpeg-full)")
            ctx.log.for_stage("assemble").warn(notes[-1])
        finalize(raw, final, "08_captions/captions.ass", measured, reel.loudness_lufs, reel.true_peak_dbtp, ac.lra, ac.crf,
                 ac.preset, ac.pix_fmt, reel.fps, reel.audio_sample_rate, reel.audio_bitrate_kbps, ac.font_dirs, cwd=ctx.job.path)
        (out_dir / "assemble.json").write_text(json.dumps({"duration": round(total, 3), "segments": len(segs),
                                                           "measured_loudness": measured}, indent=2), encoding="utf-8")
        ctx.job.set_state("rendered")
        ctx.log.for_stage("assemble").info(f"final.mp4 {total:.1f}s", loudness_in=(measured or {}).get("input_i"))
        return StageResult(artifacts=["09_final/final.mp4", "09_final/assemble.json"], notes=notes)
