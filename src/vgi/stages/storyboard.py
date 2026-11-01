from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..core.stage import RunContext, Stage, StageResult
from .script import load_plan


class StoryboardStage(Stage):
    name = "storyboard"
    requires = ("script", "keyframes")

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        d = super().inputs(ctx)
        d["plan_hash"] = ctx.job.plan_hash()
        return d

    def run(self, ctx: RunContext) -> StageResult:
        plan = load_plan(ctx)
        research = json.loads((ctx.job.dir("research") / "research.json").read_text(encoding="utf-8"))
        kf_index = json.loads((ctx.job.dir("keyframes") / "keyframes.json").read_text(encoding="utf-8"))
        fact_md = ctx.job.dir("research") / "fact_sheet.md"
        env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
                          autoescape=select_autoescape(["html"]))
        tpl = env.get_template(ctx.stage_cfg("storyboard").template)
        total = sum(s.target_seconds for s in plan.scenes)
        html = tpl.render(job=ctx.job.manifest, plan=plan, research=research, kf_index=kf_index,
                          fact_md=fact_md.read_text(encoding="utf-8") if fact_md.exists() else "",
                          total_seconds=round(total, 1), stage_notes=ctx.job.record("script").notes,
                          caption=(ctx.job.dir("script") / "caption.txt").read_text(encoding="utf-8"))
        out = ctx.job.dir("storyboard") / "preview.html"
        out.write_text(html, encoding="utf-8")
        if ctx.job.manifest.state in ("created", "planned"):
            ctx.job.set_state("planned")
        return StageResult(artifacts=["04_storyboard/preview.html"])
