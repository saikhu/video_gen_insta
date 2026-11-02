from __future__ import annotations

import json
from typing import Any

from ..core.hashing import derive_seed
from ..core.stage import RunContext, Stage, StageResult
from ..media import sound
from ..media.ffmpeg import (
    finalize,
    grade_filters,
    has_audio,
    has_libass,
    loudnorm_measure,
    make_shot_segment,
    mux_audio,
    video_duration,
    xfade_chain,
)
from .tts import load_tts
from .video import load_clips, timeline_for


class AssembleStage(Stage):
    """shots → per-boundary picture transitions; clip sound → one continuous location track; narration on top;
    grade + captions + loudness → mp4."""

    name = "assemble"
    requires = ("video", "tts", "captions", "music")

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        d = super().inputs(ctx)
        d["reel"] = ctx.cfg.global_.reel.model_dump()
        d["mix"] = sound.MIX_VERSION
        return d

    def run(self, ctx: RunContext) -> StageResult:
        ac, vc, mc = ctx.stage_cfg("assemble"), ctx.stage_cfg("video"), ctx.stage_cfg("music")
        sc = ac.sound
        reel = ctx.cfg.global_.reel
        sr = reel.audio_sample_rate
        tl = timeline_for(ctx)
        clips = {c["shot_id"]: c for c in load_clips(ctx)}
        missing = [s.shot_id for s in tl.shots if s.shot_id not in clips]
        if missing:
            raise RuntimeError(f"no clips for shot(s) {missing}; run the video stage first")
        tts = {a.scene_id: a for a in load_tts(ctx)}
        music = json.loads((ctx.job.dir("music") / "music.json").read_text(encoding="utf-8"))
        bed_path = ctx.job.path / music["bed"] if music.get("bed") else None
        out_dir = ctx.job.dir("assemble")
        work = out_dir / "work"
        work.mkdir(exist_ok=True)
        log = ctx.log.for_stage("assemble")

        # picture
        segs = []
        for s in tl.shots:
            seg = work / f"seg_{s.shot_id.replace('.', '_')}.mp4"
            make_shot_segment(ctx.job.path / clips[s.shot_id]["path"], seg, s.length, reel.width, reel.height, reel.fps)
            segs.append(seg)
        cut = work / "cut.mp4"
        total = xfade_chain(segs, [s.own for s in tl.shots], [(s.transition_out, s.overlap) for s in tl.shots[:-1]],
                            cut, reel.fps)
        vdur = video_duration(cut)
        if vdur < total - 0.15:
            raise RuntimeError(f"joined video is {vdur:.2f}s but the timeline is {total:.2f}s (a transition failed)")

        # sound
        shots: list[sound.ShotSound] = []
        for s in tl.shots:
            clip = ctx.job.path / clips[s.shot_id]["path"]
            audio = sound.decode_audio(clip, sr) if vc.native_audio and has_audio(clip) else None
            sh = sound.ShotSound(s.shot_id, s.start, s.overlap, audio)
            sound.prepare_shot(sh, sr, sc, sc.voice_db)
            shots.append(sh)
        location = sound.layout(shots, total, sr, sc) if any(s.info.get("used") for s in shots) else None
        narration = [(sound.decode_audio(ctx.job.path / tts[b.beat_id].wav, sr), b.speech_start)
                     for b in tl.beats if tts[b.beat_id].duration > 0]
        bed = sound.decode_audio(bed_path, sr) if bed_path and bed_path.exists() and has_audio(bed_path) else None
        seed = derive_seed(ctx.cfg.global_.seed_base, "room_tone", 0, "assemble")
        mix, mix_report = sound.mix_reel(narration, location, bed, total, sr, sc, seed,
                                         bed_gap_db=mc.bed_gain_db, bed_duck_db=mc.duck_db)
        sound.write_wav(work / "mix.wav", mix, sr)
        if location is not None:
            sound.write_wav(work / "location.wav", location, sr)
        mixed = work / "mixed.mp4"
        mux_audio(cut, work / "mix.wav", mixed, total, sr)
        gaps = sound.silent_gaps(mix, sr, skip_tail=sc.end_fade_s + 0.1)

        measured = loudnorm_measure(mixed, reel.loudness_lufs, reel.true_peak_dbtp, ac.lra) if ac.loudnorm_two_pass else None
        final = out_dir / "final.mp4"
        notes = []
        if not has_libass():
            notes.append("captions NOT burned in: ffmpeg lacks libass (install ffmpeg-full)")
            log.warn(notes[-1])
        dropped = [s.shot_id for s in shots if not s.info.get("used")]
        if dropped:
            notes.append(f"shots with no usable sound (covered by neighbours): {dropped}")
        if gaps:
            notes.append(f"silent gaps in the mix at {gaps[:8]} s")
            log.warn(notes[-1])
        finalize(mixed, final, "08_captions/captions.ass", measured, reel.loudness_lufs, reel.true_peak_dbtp, ac.lra, ac.crf,
                 ac.preset, ac.pix_fmt, reel.fps, sr, reel.audio_bitrate_kbps, ac.font_dirs,
                 cwd=ctx.job.path, grade=grade_filters(getattr(ac, "grade", None)))
        report = {"duration": total, "shots": len(segs), "beats": len(tl.beats), "measured_loudness": measured,
                  "mix": {**mix_report, "version": sound.MIX_VERSION, "silent_gaps": gaps},
                  "shot_sound": {s.shot_id: {k: v for k, v in s.info.items() if k != "span"} for s in shots}}
        (out_dir / "assemble.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        ctx.job.set_state("rendered")
        removed = [s.info.get("music_removed_db", 0.0) for s in shots if s.info.get("used")]
        log.info(f"final.mp4 {total:.1f}s, {len(segs)} shots over {len(tl.beats)} beats; "
                 f"location sound from {len(removed)} shots"
                 + (f", tonal content removed {min(removed):.0f}-{max(removed):.0f} dB" if removed else ""),
                 loudness_in=(measured or {}).get("input_i"))
        return StageResult(artifacts=["09_final/final.mp4", "09_final/assemble.json"], notes=notes)
