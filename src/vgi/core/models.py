"""Data contracts shared between stages (versioned)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CONTRACT_VERSION = 1


class SourceRef(BaseModel):
    id: str
    title: str
    license: str = ""
    url: str = ""


class NumberClaim(BaseModel):
    claim: str
    source: str
    confidence: Literal["high", "medium", "low"] = "medium"


class KeyFigure(BaseModel):
    name: str
    role: str
    depiction: Literal["forbidden", "allowed"] = "forbidden"


class FactSheet(BaseModel):
    subject: str
    date: str
    location: str
    belligerents: list[str]
    numbers: list[NumberClaim]
    timeline: list[str]
    key_figures: list[KeyFigure]
    outcome: str
    significance: str
    uncertain_points: list[str]
    sources: list[SourceRef]


class Idea(BaseModel):
    premise: str
    format: str
    characters: list[str]
    punchline: str
    originality_score: float = 1.0
    similar_known: list[str] = Field(default_factory=list)


class IdeaPool(BaseModel):
    ideas: list[Idea]


class Scene(BaseModel):
    id: int
    shot_type: str
    narration_text: str
    target_seconds: float
    visual_prompt: str
    negative_prompt: str = ""
    motion_prompt: str = ""
    on_screen_text: str = ""
    keyframe_choice: int = 0


class ScenePlan(BaseModel):
    title: str
    hook: str
    scenes: list[Scene]
    music_policy: str = "none"
    cta: str = ""
    hashtags: list[str] = Field(default_factory=list)
    sources_for_caption: list[str] = Field(default_factory=list)


class WordTiming(BaseModel):
    word: str
    start: float
    end: float


class SceneAudio(BaseModel):
    scene_id: int
    wav: str
    duration: float
    words: list[WordTiming]
