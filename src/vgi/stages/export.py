from __future__ import annotations

import json
import shutil
from datetime import datetime

from .. import __version__
from ..core.stage import RunContext, Stage, StageResult
from ..media.images import to_cover_jpeg
from .keyframes import chosen_keyframe
from .script import load_plan
from .video import load_clips


class ExportStage(Stage):
    name = "export"
    requires = ("qa",)

    def run(self, ctx: RunContext) -> StageResult:
        ec, reel = ctx.stage_cfg("export"), ctx.cfg.global_.reel
        if ctx.job.manifest.state != "qa_passed" and not ctx.extra.get("override"):
            raise RuntimeError(f"job state is {ctx.job.manifest.state!r}; fix QA failures or `vgi qa --override --reason ...`")
        plan = load_plan(ctx)
        name = ec.name_template.format(job_id=ctx.job.id, title=plan.title)
        out_dir = ctx.job.dir("export")
        final = out_dir / f"{name}.mp4"
        shutil.copy2(out_dir / "final.mp4", final)
        cover_scene = next((s for s in plan.scenes if s.id == ec.cover_scene), plan.scenes[0])
        cover_shot = cover_scene.all_shots()[0]
        to_cover_jpeg(ctx.job.path / chosen_keyframe(ctx, cover_scene.shot_id(0), cover_shot.keyframe_choice), out_dir / "cover.jpg",
                      reel.width, reel.height)
        caption = (ctx.job.dir("script") / "caption.txt").read_text(encoding="utf-8")
        tags = [t for t in plan.hashtags if t.startswith("#")] + [t for t in ctx.cfg.topic.hashtags if t not in plan.hashtags]
        caption_full = (caption.strip() + "\n\n" + " ".join(tags[: ec.max_hashtags]))[: ec.caption_max_chars]
        (out_dir / "caption.txt").write_text(caption_full, encoding="utf-8")
        qa = json.loads((out_dir / "qa_report.json").read_text(encoding="utf-8"))
        meta = {
            "job_id": ctx.job.id, "title": plan.title, "topic": ctx.cfg.topic.name, "subject": ctx.job.manifest.subject,
            "exported_at": datetime.now().isoformat(), "vgi_version": __version__, "ai_generated": True,
            "env": ctx.cfg.env.name,
            "models": {k: {"backend": ctx.job.record(k).backend, "cfg": ctx.cfg.stages.get(k, {})}
                       for k in ("research", "script", "keyframes", "video", "tts", "music")},
            "clips": load_clips(ctx), "seeds": {k: ctx.job.record(k).seeds for k in ("keyframes", "video")},
            "prompt_ids": ctx.job.record("video").prompt_ids, "sources": plan.sources_for_caption,
            "qa": {"verdict": qa["verdict"], "warns": qa["warns"]}, "cost_usd": ctx.job.manifest.total_cost_usd,
            "instagram": {"is_ai_generated": True, "share_to_feed": True, "aspect": "9:16"},
        }
        (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        ctx.job.set_state("exported")
        return StageResult(artifacts=[f"09_final/{final.name}", "09_final/cover.jpg", "09_final/caption.txt", "09_final/metadata.json"])
