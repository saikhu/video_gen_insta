from __future__ import annotations

import json
from typing import Any

from ..backends.registry import image_backend
from ..core.hashing import derive_seed
from ..core.stage import RunContext, Stage, StageResult
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
        d = {"cfg": ctx.cfg.stages.get("keyframes", {}), "style": ctx.cfg.style, "seed_base": ctx.seed_base,
             "dry_run": ctx.dry_run, "negative": ctx.cfg.topic.depiction.get("negative_prompt", "")}
        if ctx.job.scene_plan_path.exists():
            plan = load_plan(ctx)
            d["scenes"] = [(s.id, s.visual_prompt, s.negative_prompt) for s in plan.scenes]  # NOT keyframe_choice
        return d

    def run(self, ctx: RunContext) -> StageResult:
        kc = ctx.stage_cfg("keyframes")
        plan = load_plan(ctx)
        backend = image_backend(ctx)
        out_dir = ctx.job.dir("keyframes")
        index: dict[str, list[str]] = {}
        seeds: list[int] = []
        log = ctx.log.for_stage("keyframes")
        for s in plan.scenes:
            if ctx.scene_filter and s.id not in ctx.scene_filter:
                continue
            prompt, neg = build_prompt(ctx, s.visual_prompt)
            if s.negative_prompt:
                neg = f"{neg}, {s.negative_prompt}" if neg else s.negative_prompt
            paths = []
            for k in range(kc.n_candidates):
                seed = derive_seed(ctx.seed_base, s.id, k, "keyframes", kc.seed_offset)
                out = out_dir / f"scene_{s.id:02d}_c{k}.png"
                backend.generate(prompt, neg, kc.gen_width, kc.gen_height, seed, out, steps=kc.steps,
                                 guidance=kc.guidance, prefix=f"{ctx.job.id}/kf/{s.id}")
                paths.append(f"03_keyframes/{out.name}")
                seeds.append(seed)
            index[str(s.id)] = paths
            log.info(f"scene {s.id}: {len(paths)} candidates", backend=backend.name)
        (out_dir / "keyframes.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
        return StageResult(artifacts=["03_keyframes/keyframes.json", *[p for ps in index.values() for p in ps]],
                           seeds=seeds, backend=backend.name)


def chosen_keyframe(ctx: RunContext, scene_id: int, choice: int) -> str:
    index = json.loads((ctx.job.dir("keyframes") / "keyframes.json").read_text(encoding="utf-8"))
    paths = index[str(scene_id)]
    return paths[min(max(0, choice), len(paths) - 1)]
