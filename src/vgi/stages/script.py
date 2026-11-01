from __future__ import annotations

import json
from typing import Any

from ..core.models import ScenePlan
from ..core.stage import RunContext, Stage, StageResult
from ..llm import get_llm
from ..topics import get_plugin


class ScriptStage(Stage):
    name = "script"
    requires = ("research",)

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        d = super().inputs(ctx)
        d["llm"] = "stub" if (ctx.dry_run or not ctx.secrets.has_claude()) else ctx.stage_cfg("script").backend
        d["topic_rules"] = {"depiction": ctx.cfg.topic.depiction, "narration": ctx.cfg.topic.narration}
        return d

    def run(self, ctx: RunContext) -> StageResult:
        plugin = get_plugin(ctx.cfg.topic.plugin)
        research = json.loads((ctx.job.dir("research") / "research.json").read_text(encoding="utf-8"))
        llm = get_llm(ctx, "script")
        plan, cost = plugin.script(ctx, llm, research)
        errors, warns = plugin.validate(ctx, plan)
        log = ctx.log.for_stage("script")
        for w in warns:
            log.warn(w)
        if errors:
            (ctx.job.dir("script") / "scene_plan.rejected.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
            raise RuntimeError("scene plan rejected by validators:\n- " + "\n- ".join(errors))
        out = ctx.job.dir("script")
        ctx.job.scene_plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        (out / "narration.txt").write_text("\n\n".join(f"[{s.id}] {s.narration_text}" for s in plan.scenes), encoding="utf-8")
        (out / "caption.txt").write_text(plugin.caption(ctx, plan, research), encoding="utf-8")
        return StageResult(artifacts=["02_script/scene_plan.json", "02_script/narration.txt", "02_script/caption.txt"],
                           cost_usd=cost, notes=warns, backend=llm.name)


def load_plan(ctx: RunContext) -> ScenePlan:
    return ScenePlan.model_validate_json(ctx.job.scene_plan_path.read_text(encoding="utf-8"))
