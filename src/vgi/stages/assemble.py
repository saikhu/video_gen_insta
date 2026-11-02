from __future__ import annotations

import json
from typing import Any

from ..core.stage import RunContext, Stage, StageResult
from ..media.ffmpeg import (finalize, grade_filters, has_libass, loudnorm_measure, make_shot_segment, mix_narration,
                            video_duration, xfade_chain)
from .tts import load_tts
from .video import load_clips, timeline_for


class AssembleStage(Stage):
    """shots → per-boundary transitions → continuous narration over ducked diegetic sound → grade + captions → mp4."""

    name = "assemble"
    requires = ("video", "tts", "captions", "music")

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        d = super().inputs(ctx)
        d["reel"] = ctx.cfg.global_.reel.model_dump()
        return d

    def run(self, ctx: RunContext) -> StageResult:
        ac, vc, mc = ctx.stage_cfg("assemble"), ctx.stage_cfg("video"), ctx.stage_cfg("music")
        reel = ctx.cfg.global_.reel
        tl = timeline_for(ctx)
        clips = {c["shot_id"]: c for c in load_clips(ctx)}
        missing = [s.shot_id for s in tl.shots if s.shot_id not in clips]
        if missing:
            raise RuntimeError(f"no clips for shot(s) {missing}; run the video stage first")
        tts = {a.scene_id: a for a in load_tts(ctx)}
        music = json.loads((ctx.job.dir("music") / "music.json").read_text(encoding="utf-8"))
        bed = ctx.job.path / music["bed"] if music.get("bed") else None
        out_dir = ctx.job.dir("assemble")
        work = out_dir / "work"
        work.mkdir(exist_ok=True)
        log = ctx.log.for_stage("assemble")

        segs = []
        for s in tl.shots:
            seg = work / f"seg_{s.shot_id.replace('.', '_')}.mp4"
            make_shot_segment(ctx.job.path / clips[s.shot_id]["path"], seg, s.length, reel.width, reel.height, reel.fps,
                              reel.audio_sample_rate, use_clip_audio=vc.native_audio)
            segs.append(seg)
        cut = work / "cut.mp4"
        total = xfade_chain(segs, [s.own for s in tl.shots], [(s.transition_out, s.overlap) for s in tl.shots[:-1]],
                            cut, reel.fps, reel.audio_sample_rate)
        vdur = video_duration(cut)
        if vdur < total - 0.15:
            raise RuntimeError(f"joined video is {vdur:.2f}s but the timeline is {total:.2f}s (a transition failed)")
        mixed = work / "mixed.mp4"
        narration = [(ctx.job.path / tts[b.beat_id].wav, b.speech_start) for b in tl.beats if tts[b.beat_id].duration > 0]
        mix_narration(cut, narration, total, mixed, reel.audio_sample_rate,
                      diegetic_gain_db=float(getattr(ac, "diegetic_gain_db", -6.0)),
                      duck_threshold=float(getattr(ac, "duck_threshold", 0.03)),
                      duck_ratio=float(getattr(ac, "duck_ratio", 6.0)),
                      duck_release_ms=int(getattr(ac, "duck_release_ms", 450)),
                      bed=bed, bed_gain_db=mc.bed_gain_db)
        measured = loudnorm_measure(mixed, reel.loudness_lufs, reel.true_peak_dbtp, ac.lra) if ac.loudnorm_two_pass else None
        final = out_dir / "final.mp4"
        notes = []
        if not has_libass():
            notes.append("captions NOT burned in: ffmpeg lacks libass (install ffmpeg-full)")
            log.warn(notes[-1])
        finalize(mixed, final, "08_captions/captions.ass", measured, reel.loudness_lufs, reel.true_peak_dbtp, ac.lra, ac.crf,
                 ac.preset, ac.pix_fmt, reel.fps, reel.audio_sample_rate, reel.audio_bitrate_kbps, ac.font_dirs,
                 cwd=ctx.job.path, grade=grade_filters(getattr(ac, "grade", None)))
        (out_dir / "assemble.json").write_text(json.dumps({"duration": total, "shots": len(segs), "beats": len(tl.beats),
                                                           "measured_loudness": measured}, indent=2), encoding="utf-8")
        ctx.job.set_state("rendered")
        log.info(f"final.mp4 {total:.1f}s, {len(segs)} shots over {len(tl.beats)} beats",
                 loudness_in=(measured or {}).get("input_i"))
        return StageResult(artifacts=["09_final/final.mp4", "09_final/assemble.json"], notes=notes)
