from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.stage import RunContext, Stage, StageResult
from ..llm import get_llm
from ..topics import get_plugin


def _corpus_fingerprint(root: Path, corpus_dir: str) -> list[tuple[str, int, int]]:
    d = root / corpus_dir
    if not d.exists():
        return []
    return [(p.name, int(p.stat().st_mtime), p.stat().st_size) for p in sorted(d.glob("*")) if p.is_file()]


def llm_identity(ctx: RunContext, stage: str) -> list[str]:
    """What determines the LLM output: backend + model (part of the stage cache key)."""
    backend = "stub" if ctx.dry_run else getattr(ctx.stage_cfg(stage), "backend", "stub")
    llm = ctx.cfg.llm or {}
    model = {"local": llm.get("local", {}).get("model", ""), "ollama": llm.get("local", {}).get("model", ""),
             "claude": llm.get("claude", {}).get("model", "")}.get(backend, "")
    return [backend, model]


class ResearchStage(Stage):
    name = "research"

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        d = super().inputs(ctx)
        t = ctx.cfg.topic
        d.update(subject=ctx.job.manifest.subject, plugin=t.plugin,
                 corpus=_corpus_fingerprint(ctx.root, (t.model_extra or {}).get("corpus_dir", "")),
                 llm=llm_identity(ctx, "research"))
        return d

    def run(self, ctx: RunContext) -> StageResult:
        plugin = get_plugin(ctx.cfg.topic.plugin)
        llm = get_llm(ctx, "research")
        out = plugin.research(ctx, llm)
        (ctx.job.dir("research") / "research.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str),
                                                               encoding="utf-8")
        notes = ["uncited: no corpus matched"] if out.get("uncited") else []
        return StageResult(artifacts=[*out.get("artifacts", []), "01_research/research.json"], cost_usd=float(out.get("cost_usd", 0)),
                           notes=notes, backend=llm.name)
