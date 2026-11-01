from __future__ import annotations

import json
from typing import Any

from ..backends.registry import image_backend
from ..core.hashing import derive_seed, hash_obj
from ..core.stage import RunContext, Stage, StageResult, apply_reseed, load_reseeds
from .script import load_plan


def build_prompt(ctx: RunContext, visual_prompt: str) -> tuple[str, str]:
    st = ctx.cfg.style or {}
    prompt = " ".join(x for x in (st.get("prompt_prefix", ""), visual_prompt, st.get("prompt_suffix", "")) if x)
    neg = ", ".join(x for x in (ctx.cfg.topic.depiction.get("negative_prompt", ""), st.get("negative_prompt", "")) if x)
    return prompt.strip(), neg.strip()


class KeyframesStage(Stage):
    name = "keyframes"
    requires = ("script",)

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        d = {"cfg": ctx.cfg.stages.get("keyframes", {}), "style": ctx.cfg.style, "seed_base": ctx.cfg.global_.seed_base,
             "dry_run": ctx.dry_run, "negative": ctx.cfg.topic.depiction.get("negative_prompt", ""),
             "reseeds": load_reseeds(ctx.job.dir("keyframes") / "seeds.json")}
        if ctx.job.scene_plan_path.exists():
            plan = load_plan(ctx)
            d["scenes"] = [(s.id, s.visual_prompt, s.negative_prompt) for s in plan.scenes]  # NOT keyframe_choice
        return d

    def run(self, ctx: RunContext) -> StageResult:
        kc = ctx.stage_cfg("keyframes")
        plan = load_plan(ctx)
        backend = image_backend(ctx)
        out_dir = ctx.job.dir("keyframes")
        index_path = out_dir / "keyframes.json"
        index: dict[str, Any] = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
        index = {k: v for k, v in index.items() if isinstance(v, dict)}       # drop the old list-only format
        reseeds = apply_reseed(out_dir / "seeds.json", ctx.scene_filter or ([s.id for s in plan.scenes] if ctx.reseed else None), ctx.reseed)
        seeds: list[int] = []
        log = ctx.log.for_stage("keyframes")
        for s in plan.scenes:
            if ctx.scene_filter and s.id not in ctx.scene_filter:
                continue
            prompt, neg = build_prompt(ctx, s.visual_prompt)
            if s.negative_prompt:
                neg = f"{neg}, {s.negative_prompt}" if neg else s.negative_prompt
            scene_hash = hash_obj([prompt, neg, kc.model_dump(), reseeds.get(s.id, 0), ctx.dry_run, backend.name])
            prev = index.get(str(s.id))
            paths = [f"03_keyframes/scene_{s.id:02d}_c{k}.png" for k in range(kc.n_candidates)]
            if prev and prev.get("hash") == scene_hash and not ctx.force and all((ctx.job.path / p).exists() for p in paths):
                log.info(f"scene {s.id}: cached")
                index[str(s.id)] = prev
                continue
            for k in range(kc.n_candidates):
                seed = derive_seed(ctx.cfg.global_.seed_base, s.id, k, "keyframes", kc.seed_offset, reseeds.get(s.id, 0))
                out = out_dir / f"scene_{s.id:02d}_c{k}.png"
                backend.generate(prompt, neg, kc.gen_width, kc.gen_height, seed, out, steps=kc.steps,
                                 guidance=kc.guidance, prefix=f"{ctx.job.id}/kf/{s.id}")
                seeds.append(seed)
            index[str(s.id)] = {"paths": paths, "hash": scene_hash, "seeds": seeds[-kc.n_candidates:]}
            log.info(f"scene {s.id}: {len(paths)} candidates", backend=backend.name)
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        missing = [s.id for s in plan.scenes if str(s.id) not in index]
        arts = ["03_keyframes/keyframes.json", *[p for e in index.values() for p in e["paths"]]]
        return StageResult(artifacts=arts, seeds=seeds, backend=backend.name, partial=bool(missing),
                           notes=[f"scenes without keyframes yet: {missing}"] if missing else [])


def chosen_keyframe(ctx: RunContext, scene_id: int, choice: int, missing_ok: bool = False) -> str | None:
    index_path = ctx.job.dir("keyframes") / "keyframes.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    entry = index.get(str(scene_id))
    if entry is None:
        if missing_ok:
            return None
        raise KeyError(f"scene {scene_id} has no keyframes yet")
    paths = entry["paths"] if isinstance(entry, dict) else entry
    return paths[min(max(0, choice), len(paths) - 1)]
