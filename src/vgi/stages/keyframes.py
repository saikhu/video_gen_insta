from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..backends.registry import image_backend
from ..core.hashing import derive_seed, hash_obj
from ..core.stage import RunContext, Stage, StageResult, apply_reseed, load_reseeds
from .script import load_plan


def build_prompt(ctx: RunContext, visual_prompt: str, extra_negative: str = "") -> tuple[str, str]:
    st = ctx.cfg.style or {}
    prompt = " ".join(x for x in (st.get("prompt_prefix", ""), visual_prompt, st.get("prompt_suffix", "")) if x)
    neg = ", ".join(x for x in (ctx.cfg.topic.depiction.get("negative_prompt", ""), st.get("negative_prompt", ""),
                                extra_negative) if x)
    return prompt.strip(), neg.strip()


def _workers(backend) -> int:
    if getattr(backend, "name", "") == "comfy":
        return max(1, backend.pool.size)          # one image job per ComfyUI instance
    if getattr(backend, "name", "") == "stub":
        return max(1, min(8, os.cpu_count() or 4))
    return 1                                      # mflux runs in-process on the Mac's single GPU


class KeyframesStage(Stage):
    """One keyframe image per SHOT (n candidates each). The human picks candidates in the storyboard."""

    name = "keyframes"
    requires = ("script",)

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        d = {"cfg": ctx.cfg.stages.get("keyframes", {}), "style": ctx.cfg.style, "seed_base": ctx.cfg.global_.seed_base,
             "dry_run": ctx.dry_run, "negative": ctx.cfg.topic.depiction.get("negative_prompt", ""),
             "reseeds": load_reseeds(ctx.job.dir("keyframes") / "seeds.json")}
        if ctx.job.scene_plan_path.exists():
            plan = load_plan(ctx)
            d["shots"] = [(sc.shot_id(k), sh.visual_prompt, sc.negative_prompt)            # NOT keyframe_choice
                          for sc in plan.scenes for k, sh in enumerate(sc.all_shots())]
        return d

    def run(self, ctx: RunContext) -> StageResult:
        kc = ctx.stage_cfg("keyframes")
        plan = load_plan(ctx)
        backend = image_backend(ctx)
        out_dir = ctx.job.dir("keyframes")
        index_path = out_dir / "keyframes.json"
        index: dict[str, Any] = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
        index = {k: v for k, v in index.items() if isinstance(v, dict) and "." in k}     # drop pre-shot formats
        reseeds = apply_reseed(out_dir / "seeds.json",
                               ctx.scene_filter or ([s.id for s in plan.scenes] if ctx.reseed else None), ctx.reseed)
        log = ctx.log.for_stage("keyframes")
        jobs = []
        for sc in plan.scenes:
            if ctx.scene_filter and sc.id not in ctx.scene_filter:
                continue
            for k, sh in enumerate(sc.all_shots()):
                sid = sc.shot_id(k)
                prompt, neg = build_prompt(ctx, sh.visual_prompt, sc.negative_prompt)
                h = hash_obj([prompt, neg, kc.model_dump(), reseeds.get(sc.id, 0), ctx.dry_run, backend.name])
                stem = f"shot_{sc.id:02d}_{k + 1}"
                paths = [f"03_keyframes/{stem}_c{c}.png" for c in range(kc.n_candidates)]
                prev = index.get(sid)
                if prev and prev.get("hash") == h and not ctx.force and all((ctx.job.path / p).exists() for p in paths):
                    continue
                for c in range(kc.n_candidates):
                    seed = derive_seed(ctx.cfg.global_.seed_base, sid, c, "keyframes", kc.seed_offset, reseeds.get(sc.id, 0))
                    jobs.append((sid, c, seed, prompt, neg, out_dir / f"{stem}_c{c}.png"))
                index[sid] = {"paths": paths, "hash": h, "seeds": []}

        def gen(job):
            sid, c, seed, prompt, neg, out = job
            backend.generate(prompt, neg, kc.gen_width, kc.gen_height, seed, out, steps=kc.steps, guidance=kc.guidance,
                             prefix=f"{ctx.job.id}/kf/{sid}")
            return sid, c, seed

        workers = _workers(backend)
        log.info(f"{len(jobs)} images to render with {workers} worker(s)", backend=backend.name)
        seeds: list[int] = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for sid, c, seed in ex.map(gen, jobs):
                index[sid]["seeds"].append(seed)
                seeds.append(seed)
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        missing = [sid for sid in plan.shot_ids() if sid not in index]
        arts = ["03_keyframes/keyframes.json", *[p for e in index.values() for p in e["paths"]]]
        return StageResult(artifacts=arts, seeds=seeds, backend=backend.name, partial=bool(missing),
                           notes=[f"shots without keyframes yet: {missing}"] if missing else [])


def chosen_keyframe(ctx: RunContext, shot_id: str | int, choice: int, missing_ok: bool = False) -> str | None:
    index_path = ctx.job.dir("keyframes") / "keyframes.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    key = str(shot_id) if "." in str(shot_id) else f"{shot_id}.1"
    entry = index.get(key) or index.get(str(shot_id))
    if entry is None:
        if missing_ok:
            return None
        raise KeyError(f"shot {key} has no keyframes yet")
    paths = entry["paths"] if isinstance(entry, dict) else entry
    return paths[min(max(0, choice), len(paths) - 1)]
