"""Stage DAG and command-level orchestration."""
from __future__ import annotations

from .stage import RunContext, Stage

PLAN_STAGES = ["research", "script", "keyframes", "storyboard"]
RENDER_STAGES = ["tts", "video", "music", "captions", "assemble"]
POST_STAGES = ["qa", "export"]
ALL_STAGES = PLAN_STAGES + RENDER_STAGES + POST_STAGES


def build_stage(name: str) -> Stage:
    from ..stages import STAGE_CLASSES  # local import avoids cycles

    return STAGE_CLASSES[name]()


def run_stages(ctx: RunContext, names: list[str]) -> None:
    for n in names:
        build_stage(n).execute(ctx)


def slice_stages(from_stage: str | None, until_stage: str | None) -> list[str]:
    names = list(ALL_STAGES)
    if from_stage:
        names = names[names.index(from_stage):]
    if until_stage:
        names = names[: names.index(until_stage) + 1]
    return names
