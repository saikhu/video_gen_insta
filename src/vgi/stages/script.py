from __future__ import annotations

import json
from typing import Any

from ..core.models import ScenePlan
from ..core.stage import RunContext, Stage, StageResult
from ..llm import get_llm
from .research import llm_identity
from ..topics import get_plugin


class ScriptStage(Stage):
    name = "script"
    requires = ("research",)

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        d = super().inputs(ctx)
        d["llm"] = llm_identity(ctx, "script")
        d["topic_rules"] = {"depiction": ctx.cfg.topic.depiction, "narration": ctx.cfg.topic.narration}
        return d

    def run(self, ctx: RunContext) -> StageResult:
        plugin = get_plugin(ctx.cfg.topic.plugin)
        research = json.loads((ctx.job.dir("research") / "research.json").read_text(encoding="utf-8"))
        llm = get_llm(ctx, "script")
        plan, cost = plugin.script(ctx, llm, research)
        log = ctx.log.for_stage("script")
        sc = ctx.stage_cfg("script")
        history: list[dict] = []
        fixes: list[str] = []
        for round_ in range(int(getattr(sc, "repair_rounds", 2)) + 1):
            plan, notes = plugin.autofix(ctx, plan)
            fixes += notes
            errors, warns = plugin.validate(ctx, plan)
            review, rcost = plugin.review(ctx, llm, plan, research) if not errors else ([], 0.0)
            cost += rcost
            todo = errors + plugin.fixable(warns) + review
            history.append({"round": round_, "autofix": notes, "errors": errors, "warnings": warns, "review": review})
            if not todo or round_ == int(getattr(sc, "repair_rounds", 2)):
                break
            log.info(f"repair round {round_ + 1}: {len(todo)} issue(s)", issues=todo[:12])
            plan, rc = plugin.repair(ctx, llm, plan, todo)
            cost += rc
        (ctx.job.dir("script") / "review.json").write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
        warns = warns + [f"unresolved review: {r}" for r in review]
        for w in warns:
            log.warn(w)
        if errors:
            (ctx.job.dir("script") / "scene_plan.rejected.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
            raise RuntimeError("scene plan rejected by validators:\n- " + "\n- ".join(errors))
        out = ctx.job.dir("script")
        ctx.job.scene_plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        (out / "narration.txt").write_text("\n\n".join(f"[{s.id}] {s.narration_text}" for s in plan.scenes), encoding="utf-8")
        (out / "caption.txt").write_text(plugin.caption(ctx, plan, research), encoding="utf-8")
        arts = ["02_script/scene_plan.json", "02_script/narration.txt", "02_script/caption.txt", "02_script/review.json"]
        if (out / "treatment.md").exists():
            arts.append("02_script/treatment.md")
        ctx.log.for_stage("script").info(f"{len(plan.scenes)} beats, {len(plan.shot_ids())} shots", backend=llm.name)
        return StageResult(artifacts=arts, cost_usd=cost, notes=warns, backend=llm.name)


def load_plan(ctx: RunContext) -> ScenePlan:
    return ScenePlan.model_validate_json(ctx.job.scene_plan_path.read_text(encoding="utf-8"))
