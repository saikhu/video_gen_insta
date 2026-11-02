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


Transition = Literal["cut", "fade", "fadeblack", "flash"]


class Shot(BaseModel):
    """One camera shot: one keyframe → one video clip. Several shots can play under one narration beat."""

    shot_type: str
    visual_prompt: str
    motion_prompt: str = ""
    sound_prompt: str = ""        # diegetic sound for the video model (wind, hooves...), never music for the Islamic track
    weight: float = 1.0           # share of the beat's duration
    keyframe_choice: int = 0


class Scene(BaseModel):
    """A narration beat: one or two spoken sentences, with 1-3 shots cut underneath."""

    id: int
    narration_text: str
    shots: list[Shot] = Field(default_factory=list)
    on_screen_text: str = ""      # short title card shown at the start of the beat (hook, date, place)
    transition: Transition = "cut"  # transition INTO this beat
    pause_after: float = 0.0      # dramatic silence after the line (sound swells), seconds
    # legacy single-shot fields (plans written before shots existed)
    shot_type: str = ""
    visual_prompt: str = ""
    motion_prompt: str = ""
    negative_prompt: str = ""
    target_seconds: float = 0.0
    keyframe_choice: int = 0

    def all_shots(self) -> list[Shot]:
        if self.shots:
            return self.shots
        return [Shot(shot_type=self.shot_type or "wide", visual_prompt=self.visual_prompt, motion_prompt=self.motion_prompt,
                     keyframe_choice=self.keyframe_choice)]

    def shot_id(self, k: int) -> str:
        return f"{self.id}.{k + 1}"


class ScenePlan(BaseModel):
    title: str
    hook: str
    scenes: list[Scene]
    music_policy: str = "none"
    cta: str = ""
    hashtags: list[str] = Field(default_factory=list)
    sources_for_caption: list[str] = Field(default_factory=list)

    def shot_ids(self) -> list[str]:
        return [sc.shot_id(k) for sc in self.scenes for k in range(len(sc.all_shots()))]

    def to_draft(self) -> "ScriptDraft":
        beats = [DraftBeat(narration=s.narration_text, on_screen_text=s.on_screen_text, transition=s.transition,
                           pause_after=s.pause_after,
                           shots=[DraftShot(shot_type=sh.shot_type, visual_prompt=sh.visual_prompt,
                                            motion_prompt=sh.motion_prompt, sound_prompt=sh.sound_prompt)
                                  for sh in s.all_shots()]) for s in self.scenes]
        return ScriptDraft(title=self.title, hook=self.hook, beats=beats, cta=self.cta, hashtags=self.hashtags,
                           sources_for_caption=self.sources_for_caption)

    def find_shot(self, shot_id: str) -> tuple[Scene, int, Shot]:
        beat, _, k = shot_id.partition(".")
        sc = next(s for s in self.scenes if s.id == int(beat))
        idx = int(k) - 1 if k else 0
        return sc, idx, sc.all_shots()[idx]


# ---- what the LLM fills (kept small; converted into ScenePlan) ----
class DraftShot(BaseModel):
    shot_type: str
    visual_prompt: str
    motion_prompt: str
    sound_prompt: str


class DraftBeat(BaseModel):
    narration: str
    on_screen_text: str
    transition: Transition
    pause_after: float
    shots: list[DraftShot]


class ScriptDraft(BaseModel):
    title: str
    hook: str
    beats: list[DraftBeat]
    cta: str
    hashtags: list[str]
    sources_for_caption: list[str]

    def to_plan(self, music_policy: str) -> ScenePlan:
        scenes = [Scene(id=i + 1, narration_text=b.narration.strip(), on_screen_text=b.on_screen_text.strip(),
                        transition="cut" if i == 0 else b.transition, pause_after=max(0.0, min(2.0, b.pause_after)),
                        shots=[Shot(**sh.model_dump()) for sh in b.shots])
                  for i, b in enumerate(self.beats)]
        return ScenePlan(title=self.title, hook=self.hook, scenes=scenes, music_policy=music_policy, cta=self.cta,
                         hashtags=self.hashtags, sources_for_caption=self.sources_for_caption)


class ReviewIssue(BaseModel):
    beat: int
    problem: str
    fix: str


class ScriptReview(BaseModel):
    issues: list[ReviewIssue]


class WordTiming(BaseModel):
    word: str
    start: float
    end: float


class SceneAudio(BaseModel):
    scene_id: int
    wav: str
    duration: float
    words: list[WordTiming]
