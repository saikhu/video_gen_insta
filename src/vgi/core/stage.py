"""Stage base class and run context."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..config import MergedConfig, Secrets
from .hashing import hash_obj
from .job import Job
from .logging import JobLogger


@dataclass
class RunContext:
    root: Path
    job: Job
    cfg: MergedConfig
    secrets: Secrets
    dry_run: bool = False
    force: bool = False
    scene_filter: list[int] | None = None
    reseed: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def log(self) -> JobLogger:
        return JobLogger(self.job.log_dir)

    def stage_cfg(self, name: str) -> BaseModel:
        return self.cfg.stage(name)

    @property
    def seed_base(self) -> int:
        return int(self.cfg.global_.seed_base)


@dataclass
class StageResult:
    artifacts: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    notes: list[str] = field(default_factory=list)
    seeds: list[int] = field(default_factory=list)
    prompt_ids: list[str] = field(default_factory=list)
    backend: str = ""
    partial: bool = False          # True when a --scene run left other scenes untouched (stage must rerun later)


def load_reseeds(path: Path) -> dict[int, int]:
    """Per-scene reseed counters ({scene_id: n}); `--scene N --reseed k` adds k to scene N only."""
    import json

    if not path.exists():
        return {}
    return {int(k): int(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def apply_reseed(path: Path, scene_ids: list[int] | None, bump: int) -> dict[int, int]:
    import json

    counters = load_reseeds(path)
    if bump:
        if not scene_ids:
            raise ValueError("--reseed needs --scene (or pass all scene ids explicitly)")
        for sid in scene_ids:
            counters[sid] = counters.get(sid, 0) + bump
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(counters, indent=2), encoding="utf-8")
    return counters


class Stage(ABC):
    name: str = ""
    requires: tuple[str, ...] = ()

    def inputs(self, ctx: RunContext) -> dict[str, Any]:
        """Output-determining inputs. Default: the stage config + hashes of required stages."""
        data: dict[str, Any] = {"cfg": ctx.cfg.stages.get(self.name, {}), "seed_base": ctx.seed_base,
                                "dry_run": ctx.dry_run}
        for r in self.requires:
            rec = ctx.job.record(r)
            data[f"dep:{r}"] = [rec.inputs_hash, rec.status, hash_obj(rec.artifacts)]
        return data

    def inputs_hash(self, ctx: RunContext) -> str:
        return hash_obj(self.inputs(ctx))

    def artifacts_exist(self, ctx: RunContext) -> bool:
        rec = ctx.job.record(self.name)
        return bool(rec.artifacts) and all((ctx.job.path / a).exists() for a in rec.artifacts)

    @abstractmethod
    def run(self, ctx: RunContext) -> StageResult: ...

    def execute(self, ctx: RunContext) -> StageResult | None:
        job = ctx.job
        rec = job.record(self.name)
        h = self.inputs_hash(ctx)
        log = ctx.log.for_stage(self.name)
        if not ctx.force and rec.status == "done" and rec.inputs_hash == h and self.artifacts_exist(ctx):
            log.info("cached, skipping", inputs_hash=h)
            return None
        partial_deps = [r for r in self.requires if job.record(r).status == "partial"]
        if partial_deps and not ctx.scene_filter and self.name not in ("keyframes", "video"):
            raise RuntimeError(f"{self.name}: upstream stage(s) {partial_deps} are partial (a --scene run); "
                               f"run the full stage first (e.g. `vgi render <job>`)")
        rec.status, rec.started, rec.inputs_hash, rec.finished = "running", time.time(), h, None
        job.save()
        log.info("start", inputs_hash=h)
        try:
            result = self.run(ctx)
        except Exception as e:  # noqa: BLE001
            rec.status = "failed"
            rec.notes.append(f"{type(e).__name__}: {e}")
            rec.finished = time.time()
            job.save()
            log.error("failed", error=str(e))
            raise
        rec.status = "partial" if result.partial else "done"
        rec.artifacts = result.artifacts
        rec.cost_usd = result.cost_usd
        rec.seeds = result.seeds
        rec.prompt_ids = result.prompt_ids
        rec.backend = result.backend
        rec.notes = result.notes
        rec.finished = time.time()
        job.save()
        log.info("done", seconds=round(rec.finished - rec.started, 1), cost_usd=result.cost_usd,
                 artifacts=len(result.artifacts))
        return result
