from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..backends.registry import video_backend
from ..core.hashing import derive_seed, hash_file
from ..core.stage import RunContext, Stage, StageResult
from ..media.ffmpeg import extract_frame, frames_for, run
from .keyframes import build_prompt, chosen_keyframe
from .script import load_plan
from .tts import load_tts


def scene_seconds(narration_s: float, xfade: float, tail: float) -> float:
    """Segment duration: lead-in (= xfade) + narration + tail (>= xfade so narration never straddles a transition)."""
    return round(xfade + narration_s + max(tail, xfade), 3)


class VideoStage(Stage):
    name = "video"
    requires = ("keyframes", "tts")

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        vc = ctx.stage_cfg("video")
        d: dict[str, Any] = {"cfg": ctx.cfg.stages.get("video", {}), "seed_base": ctx.seed_base, "dry_run": ctx.dry_run,
                             "style": ctx.cfg.style}
        if ctx.job.scene_plan_path.exists() and (ctx.job.dir("tts") / "tts.json").exists():
            durs = {a.scene_id: a.duration for a in load_tts(ctx)}
            scenes = []
            for s in load_plan(ctx).scenes:
                kf = chosen_keyframe(ctx, s.id, s.keyframe_choice)
                secs = scene_seconds(durs.get(s.id, 0.0), vc.xfade_seconds, vc.tail_seconds)
                frames = frames_for(secs, vc.fps, vc.frame_grid)   # frame count, not audio hash
                scenes.append((s.id, s.visual_prompt, s.motion_prompt, kf, hash_file(ctx.job.path / kf), frames))
            d["scenes"] = scenes
        return d

    def run(self, ctx: RunContext) -> StageResult:
        vc = ctx.stage_cfg("video")
        plan = load_plan(ctx)
        durs = {a.scene_id: a.duration for a in load_tts(ctx)}
        primary, fallback = video_backend(ctx)
        out_dir = ctx.job.dir("video")
        log = ctx.log.for_stage("video")
        clips: list[dict[str, Any]] = []
        seeds: list[int] = []
        prompt_ids: list[str] = []
        notes: list[str] = []
        targets = [s for s in plan.scenes if not ctx.scene_filter or s.id in ctx.scene_filter]
        workers = primary.workers if primary is not None else max(1, min(4, (os.cpu_count() or 4) // 2))

        def render(s) -> dict[str, Any]:
            kf = ctx.job.path / chosen_keyframe(ctx, s.id, s.keyframe_choice)
            secs = scene_seconds(durs[s.id], vc.xfade_seconds, vc.tail_seconds)
            frames = frames_for(secs, vc.fps, vc.frame_grid)
            seed = derive_seed(ctx.seed_base, s.id, 0, "video")
            out = out_dir / f"scene_{s.id:02d}.mp4"
            used, note, pid = "ken_burns", None, None
            prompt, neg = build_prompt(ctx, f"{s.visual_prompt}. {s.motion_prompt}")
            if primary is not None:
                try:
                    self._generate_chained(ctx, primary, kf, out, secs, frames, seed, prompt, neg, s.id)
                    used = primary.name
                    pf = out.with_suffix(".prompt_id")
                    pid = pf.read_text().strip() if pf.exists() else None
                except Exception as e:  # noqa: BLE001
                    log.warn(f"scene {s.id}: {primary.name} failed ({e}); falling back to {vc.fallback}")
                    note = f"scene {s.id}: fallback ken_burns after error: {str(e)[:160]}"
                    fallback.generate(kf, out, secs, seed)
            else:
                fallback.generate(kf, out, secs, seed)
            log.info(f"scene {s.id}: {secs:.2f}s ({frames} frames) via {used}")
            return {"scene_id": s.id, "path": f"06_clips/{out.name}", "seconds": secs, "frames": frames, "backend": used,
                    "seed": seed, "narration_seconds": durs[s.id], "_note": note, "_pid": pid}

        log.info(f"rendering {len(targets)} scenes with {workers} worker(s)")
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(render, targets))
        for r in sorted(results, key=lambda r: r["scene_id"]):
            seeds.append(r["seed"])
            if r["_note"]:
                notes.append(r["_note"])
            if r["_pid"]:
                prompt_ids.append(r["_pid"])
            clips.append({k: v for k, v in r.items() if not k.startswith("_")})
        (out_dir / "clips.json").write_text(json.dumps(clips, indent=2), encoding="utf-8")
        return StageResult(artifacts=["06_clips/clips.json", *[c["path"] for c in clips]], seeds=seeds,
                           prompt_ids=prompt_ids, notes=notes, backend=primary.name if primary else "ken_burns")

    def _generate_chained(self, ctx: RunContext, backend, keyframe: Path, out: Path, secs: float, frames: int,
                          seed: int, prompt: str, neg: str, scene_id: int) -> None:
        """Scenes longer than max_clip_seconds are chained: I2V, then FLF2V from the previous last frame."""
        vc = ctx.stage_cfg("video")
        max_s = vc.max_clip_seconds
        common = dict(prompt=prompt, negative=neg, width=vc.base_width, height=vc.base_height, steps=vc.steps, fps=vc.fps,
                      upscale=vc.upscale)
        if secs <= max_s:
            backend.generate(keyframe, out, secs, seed, frames=frames, prefix=f"{ctx.job.id}/clip/{scene_id}", **common)
            return
        parts: list[Path] = []
        remaining, i, first = secs, 0, keyframe
        while remaining > 0.05:
            chunk = min(max_s, remaining)
            part = out.with_name(f"{out.stem}_part{i}.mp4")
            backend.generate(first, part, chunk, seed + i, frames=frames_for(chunk, vc.fps, vc.frame_grid),
                             prefix=f"{ctx.job.id}/clip/{scene_id}_{i}", last_frame=None, **common)
            parts.append(part)
            last = out.with_name(f"{out.stem}_last{i}.png")
            extract_frame(part, max(0.0, chunk - 1.0 / vc.fps), last)
            first = last
            remaining -= chunk
            i += 1
        lst = out.with_suffix(".concat.txt")
        lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])


def load_clips(ctx: RunContext) -> list[dict[str, Any]]:
    return json.loads((ctx.job.dir("video") / "clips.json").read_text(encoding="utf-8"))
