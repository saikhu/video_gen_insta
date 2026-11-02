"""Job directory + manifest state machine."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .hashing import hash_file

STATES = ["created", "planned", "approved", "rendered", "qa_passed", "qa_failed", "exported", "published"]

STAGE_DIRS = {
    "research": "01_research",
    "script": "02_script",
    "keyframes": "03_keyframes",
    "storyboard": "04_storyboard",
    "tts": "05_tts",
    "video": "06_clips",
    "music": "07_music",
    "captions": "08_captions",
    "assemble": "09_final",
    "qa": "09_final",
    "export": "09_final",
    "publish": "10_publish",
}


class StageRecord(BaseModel):
    status: str = "pending"            # pending | running | done | failed | skipped
    inputs_hash: str = ""
    artifacts: list[str] = Field(default_factory=list)
    prompt_ids: list[str] = Field(default_factory=list)
    seeds: list[int] = Field(default_factory=list)
    started: float | None = None
    finished: float | None = None
    cost_usd: float = 0.0
    retries: int = 0
    notes: list[str] = Field(default_factory=list)
    backend: str = ""


class Manifest(BaseModel):
    contract_version: int = 1
    job_id: str
    topic: str
    subject: str
    state: str = "created"
    created_at: str = ""
    env_used: str = ""
    content_config: dict[str, Any] = Field(default_factory=dict)
    approved_plan_hash: str = ""
    stages: dict[str, StageRecord] = Field(default_factory=dict)
    total_cost_usd: float = 0.0


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s[:40] or "job"


class Job:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.manifest_path = self.path / "manifest.json"
        self.manifest: Manifest = self._load()

    # ---------- construction ----------
    @classmethod
    def create(cls, jobs_root: Path, topic: str, subject: str, content_config: dict[str, Any]) -> "Job":
        job_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{slugify(subject)}"
        path = Path(jobs_root) / job_id
        path.mkdir(parents=True, exist_ok=False)
        for d in set(STAGE_DIRS.values()):
            (path / d).mkdir(exist_ok=True)
        (path / "logs").mkdir(exist_ok=True)
        m = Manifest(job_id=job_id, topic=topic, subject=subject, created_at=datetime.now().isoformat(),
                     content_config=content_config)
        with (path / "manifest.json").open("w", encoding="utf-8") as f:
            f.write(m.model_dump_json(indent=2))
        return cls(path)

    @classmethod
    def find(cls, jobs_root: Path, ref: str) -> "Job":
        root = Path(jobs_root)
        if ref in ("latest", "last"):                     # job ids start with a timestamp
            jobs = sorted(p for p in root.glob("*") if (p / "manifest.json").exists())
            if not jobs:
                raise FileNotFoundError(f"no jobs under {root}")
            return cls(jobs[-1])
        direct = root / ref
        if direct.exists():
            return cls(direct)
        matches = sorted(p for p in root.glob(f"*{ref}*") if (p / "manifest.json").exists())
        if len(matches) == 1:
            return cls(matches[0])
        if not matches:
            raise FileNotFoundError(f"no job matching {ref!r} under {root}")
        raise ValueError(f"ambiguous job ref {ref!r}: " + ", ".join(p.name for p in matches))

    def _load(self) -> Manifest:
        with self.manifest_path.open("r", encoding="utf-8") as f:
            return Manifest.model_validate(json.load(f))

    def save(self) -> None:
        self.manifest.total_cost_usd = round(sum(r.cost_usd for r in self.manifest.stages.values()), 6)
        tmp = self.manifest_path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            f.write(self.manifest.model_dump_json(indent=2))
        tmp.replace(self.manifest_path)

    # ---------- paths ----------
    @property
    def id(self) -> str:
        return self.manifest.job_id

    def dir(self, stage: str) -> Path:
        return self.path / STAGE_DIRS[stage]

    @property
    def log_dir(self) -> Path:
        return self.path / "logs"

    @property
    def scene_plan_path(self) -> Path:
        return self.dir("script") / "scene_plan.json"

    # ---------- state ----------
    def record(self, stage: str) -> StageRecord:
        return self.manifest.stages.setdefault(stage, StageRecord())

    def set_state(self, state: str) -> None:
        if state not in STATES:
            raise ValueError(state)
        self.manifest.state = state
        self.save()

    def plan_hash(self) -> str:
        return hash_file(self.scene_plan_path) if self.scene_plan_path.exists() else ""

    def approve(self) -> None:
        if not self.scene_plan_path.exists():
            raise RuntimeError("no scene_plan.json to approve; run `vgi plan` first")
        self.manifest.approved_plan_hash = self.plan_hash()
        self.set_state("approved")

    def is_approved(self) -> bool:
        return bool(self.manifest.approved_plan_hash) and self.manifest.approved_plan_hash == self.plan_hash()

    def invalidate_if_plan_changed(self) -> bool:
        """If the plan was edited after approval, drop back to `planned`. Returns True if it did."""
        if self.manifest.approved_plan_hash and self.manifest.approved_plan_hash != self.plan_hash():
            self.manifest.approved_plan_hash = ""
            self.set_state("planned")
            return True
        return False

    def touch(self, stage: str, **fields: Any) -> StageRecord:
        rec = self.record(stage)
        for k, v in fields.items():
            setattr(rec, k, v)
        rec.finished = rec.finished or None
        self.save()
        return rec

    def now(self) -> float:
        return time.time()
