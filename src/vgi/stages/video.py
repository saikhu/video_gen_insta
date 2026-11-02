from __future__ import annotations

import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..backends.registry import video_backend
from ..core.hashing import derive_seed, hash_file, hash_obj
from ..core.stage import RunContext, Stage, StageResult, apply_reseed, load_reseeds
from ..core.timeline import Timeline, build_timeline
from ..media.ffmpeg import extract_frame, frames_for, run
from .keyframes import build_prompt, chosen_keyframe
from .script import load_plan
from .tts import load_tts


def timeline_for(ctx: RunContext) -> Timeline:
    plan = load_plan(ctx)
    durs = {a.scene_id: a.duration for a in load_tts(ctx)}
    return build_timeline(plan, durs, ctx.stage_cfg("video"))


def shot_prompt(ctx: RunContext, sh, extra_negative: str = "") -> tuple[str, str]:
    """Video prompt = picture + camera + (optionally) sound; LTX-2.5 generates the audio track from the text."""
    vc = ctx.stage_cfg("video")
    parts = [sh.visual_prompt.rstrip(". ")]
    if sh.motion_prompt:
        parts.append(f"Camera: {sh.motion_prompt.rstrip('. ')}")
    if vc.sound_in_prompt and sh.sound_prompt:
        sound = sh.sound_prompt.rstrip(". ")
        style = getattr(vc, "sound_style", "")
        parts.append(f"Sound: {style}: {sound[:1].lower()}{sound[1:]}" if style else f"Sound: {sound}")
    prompt, neg = build_prompt(ctx, ". ".join(parts) + ".", extra_negative)
    if vc.audio_negative:
        neg = f"{neg}, {vc.audio_negative}" if neg else vc.audio_negative
    return prompt, neg


class VideoStage(Stage):
    """One clip per SHOT, rendered concurrently (one worker per healthy ComfyUI instance)."""

    name = "video"
    requires = ("keyframes", "tts")

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        d: dict[str, Any] = {"cfg": ctx.cfg.stages.get("video", {}), "seed_base": ctx.cfg.global_.seed_base,
                             "dry_run": ctx.dry_run, "style": ctx.cfg.style,
                             "reseeds": load_reseeds(ctx.job.dir("video") / "seeds.json")}
        if ctx.job.scene_plan_path.exists() and (ctx.job.dir("tts") / "tts.json").exists():
            plan, tl = load_plan(ctx), timeline_for(ctx)
            vc = ctx.stage_cfg("video")
            shots = []
            for slot in tl.shots:
                sc, k, sh = plan.find_shot(slot.shot_id)
                kf = chosen_keyframe(ctx, slot.shot_id, sh.keyframe_choice, missing_ok=True)
                shots.append((slot.shot_id, sh.visual_prompt, sh.motion_prompt, sh.sound_prompt, kf,
                              hash_file(ctx.job.path / kf) if kf else None, slot.frames(vc.fps, vc.frame_grid)))
            d["shots"] = shots
        return d

    def run(self, ctx: RunContext) -> StageResult:
        vc = ctx.stage_cfg("video")
        plan = load_plan(ctx)
        tl = timeline_for(ctx)
        primary, fallback = video_backend(ctx)
        out_dir = ctx.job.dir("video")
        log = ctx.log.for_stage("video")
        prompt_ids: list[str] = []
        notes: list[str] = [f"shots dropped (beat too short for them): {tl.dropped}"] if tl.dropped else []
        clips_path = out_dir / "clips.json"
        existing_raw = json.loads(clips_path.read_text(encoding="utf-8")) if clips_path.exists() else []
        existing = {c["shot_id"]: c for c in existing_raw if "shot_id" in c}
        reseeds = apply_reseed(out_dir / "seeds.json",
                               ctx.scene_filter or ([s.id for s in plan.scenes] if ctx.reseed else None), ctx.reseed)
        targets = [s for s in tl.shots if not ctx.scene_filter or s.beat_id in ctx.scene_filter]
        no_kf = [s.shot_id for s in targets if chosen_keyframe(ctx, s.shot_id, plan.find_shot(s.shot_id)[2].keyframe_choice,
                                                               missing_ok=True) is None]
        if no_kf:
            raise RuntimeError(f"no keyframes for shot(s) {no_kf}; run `vgi plan <job>` (optionally --scene) first")
        workers = primary.workers if primary is not None else max(1, min(4, (os.cpu_count() or 4) // 2))
        backend_name = primary.name if primary is not None else "ken_burns"

        def render(slot) -> dict[str, Any]:
            sc, k, sh = plan.find_shot(slot.shot_id)
            kf = ctx.job.path / chosen_keyframe(ctx, slot.shot_id, sh.keyframe_choice)
            secs = slot.length
            frames = slot.frames(vc.fps, vc.frame_grid)
            seed = derive_seed(ctx.cfg.global_.seed_base, slot.shot_id, 0, "video", reseeds.get(sc.id, 0))
            out = out_dir / f"shot_{sc.id:02d}_{k + 1}.mp4"
            prompt, neg = shot_prompt(ctx, sh, sc.negative_prompt)
            h = hash_obj([prompt, neg, hash_file(kf), frames, vc.model_dump(), seed, backend_name, ctx.dry_run])
            prev = existing.get(slot.shot_id)
            if prev and prev.get("hash") == h and not ctx.force and out.exists():
                log.info(f"shot {slot.shot_id}: cached ({prev['backend']})")
                return {**prev, "_note": None, "_pid": None}
            used, note, pid = "ken_burns", None, None
            if primary is not None:
                try:
                    self._generate_chained(ctx, primary, kf, out, secs, frames, seed, prompt, neg, slot.shot_id)
                    used = primary.name
                    pf = out.with_suffix(".prompt_id")
                    pid = pf.read_text().strip() if pf.exists() else None
                except Exception as e:  # noqa: BLE001
                    log.warn(f"shot {slot.shot_id}: {primary.name} failed ({e}); falling back to {vc.fallback}")
                    note = f"shot {slot.shot_id}: fallback ken_burns after error: {str(e)[:160]}"
                    fallback.generate(kf, out, secs, seed)
            else:
                fallback.generate(kf, out, secs, seed)
            log.info(f"shot {slot.shot_id}: {secs:.2f}s ({frames} frames) via {used}")
            return {"shot_id": slot.shot_id, "beat_id": sc.id, "path": f"06_clips/{out.name}", "seconds": secs,
                    "frames": frames, "backend": used, "seed": seed,
                    "hash": h if used == backend_name else None,      # fallback clips are retried next run
                    "_note": note, "_pid": pid}

        log.info(f"rendering {len(targets)} shots with {workers} worker(s)")
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(render, targets))
        merged = dict(existing)
        for r in results:
            if r["_note"]:
                notes.append(r["_note"])
            if r["_pid"]:
                prompt_ids.append(r["_pid"])
            merged[r["shot_id"]] = {k: v for k, v in r.items() if not k.startswith("_")}
        clips = [merged[s.shot_id] for s in tl.shots if s.shot_id in merged]
        missing = [s.shot_id for s in tl.shots if s.shot_id not in merged]
        if missing:
            notes.append(f"shots without clips yet: {missing}")
        clips_path.write_text(json.dumps(clips, indent=2), encoding="utf-8")
        return StageResult(artifacts=["06_clips/clips.json", *[c["path"] for c in clips]], seeds=[c["seed"] for c in clips],
                           prompt_ids=prompt_ids, notes=notes, backend=backend_name, partial=bool(missing))

    def _generate_chained(self, ctx: RunContext, backend, keyframe: Path, out: Path, secs: float, frames: int,
                          seed: int, prompt: str, neg: str, shot_id: str) -> None:
        """Shots longer than max_clip_seconds are split into equal parts, each I2V from the previous part's true
        last frame (the FLF2V template is only for an explicit end frame, which v1 does not use)."""
        vc = ctx.stage_cfg("video")
        max_s = vc.max_clip_seconds
        common = dict(prompt=prompt, negative=neg, width=vc.base_width, height=vc.base_height, steps=vc.steps, fps=vc.fps,
                      upscale=vc.upscale)
        tag = shot_id.replace(".", "_")
        if secs <= max_s:
            backend.generate(keyframe, out, secs, seed, frames=frames, prefix=f"{ctx.job.id}/clip/{tag}", **common)
            return
        parts: list[Path] = []
        pids: list[str] = []
        n_parts = math.ceil(secs / max_s)
        chunk = secs / n_parts
        remaining, i, first = secs, 0, keyframe
        while remaining > 0.05:
            part_frames = frames_for(min(chunk, remaining), vc.fps, vc.frame_grid)
            part_len = part_frames / vc.fps
            part = out.with_name(f"{out.stem}_part{i}.mp4")
            backend.generate(first, part, chunk, seed + i, frames=part_frames, prefix=f"{ctx.job.id}/clip/{tag}_{i}", **common)
            parts.append(part)
            pf = part.with_suffix(".prompt_id")
            if pf.exists():
                pids.append(pf.read_text().strip())
            last = out.with_name(f"{out.stem}_last{i}.png")
            extract_frame(part, max(0.0, part_len - 1.0 / vc.fps), last)
            first = last
            remaining -= part_len
            i += 1
        lst = out.with_suffix(".concat.txt")
        lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
        out.with_suffix(".prompt_id").write_text(",".join(pids))


def load_clips(ctx: RunContext) -> list[dict[str, Any]]:
    return json.loads((ctx.job.dir("video") / "clips.json").read_text(encoding="utf-8"))
