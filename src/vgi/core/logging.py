"""Per-job JSONL logging plus a rich console."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


class JobLogger:
    def __init__(self, log_dir: Path, stage: str | None = None, quiet: bool = False):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.stage = stage
        self.quiet = quiet

    def for_stage(self, stage: str) -> "JobLogger":
        return JobLogger(self.log_dir, stage, self.quiet)

    def event(self, kind: str, **data: Any) -> None:
        rec = {"ts": time.time(), "stage": self.stage, "kind": kind, **data}
        with (self.log_dir / f"{self.stage or 'job'}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str, ensure_ascii=False) + "\n")

    def info(self, msg: str, **data: Any) -> None:
        self.event("info", msg=msg, **data)
        if not self.quiet:
            console.print(f"[dim]{self.stage or 'job'}[/dim] {msg}")

    def warn(self, msg: str, **data: Any) -> None:
        self.event("warn", msg=msg, **data)
        if not self.quiet:
            console.print(f"[yellow]{self.stage or 'job'}[/yellow] {msg}")

    def error(self, msg: str, **data: Any) -> None:
        self.event("error", msg=msg, **data)
        if not self.quiet:
            console.print(f"[red]{self.stage or 'job'}[/red] {msg}")
