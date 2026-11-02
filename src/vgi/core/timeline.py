"""Edit timeline: where every narration beat and every shot sits on the final reel.

A beat lasts  pre-roll + narration + post-roll + pause_after.  Its shots split that time by weight.
Consecutive shots are joined by an xfade whose duration depends on the cut type (a 1-frame "cut" inside a
beat, the beat's own transition between beats). Each shot segment is rendered `own + overlap` long, so with
xfade offsets at the cumulative `own` sums the reel is exactly sum(own) long and narration placement is just
beat.start + pre. Video, captions and assembly all read this one structure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..media.ffmpeg import frames_for
from .models import ScenePlan

XFADE_NAME = {"cut": "fade", "fade": "fade", "fadeblack": "fadeblack", "flash": "fadewhite"}


@dataclass
class ShotSlot:
    beat_id: int
    k: int
    shot_id: str
    start: float
    own: float
    overlap: float = 0.0             # transition into the NEXT shot
    transition_out: str = "fade"     # xfade name into the next shot

    @property
    def length(self) -> float:
        return round(self.own + self.overlap, 3)

    def frames(self, fps: int, grid: int) -> int:
        return frames_for(self.length, fps, grid)


@dataclass
class BeatSlot:
    beat_id: int
    start: float
    pre: float
    narration: float
    post: float
    shot_ids: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return round(self.pre + self.narration + self.post, 3)

    @property
    def speech_start(self) -> float:
        return round(self.start + self.pre, 3)


@dataclass
class Timeline:
    beats: list[BeatSlot]
    shots: list[ShotSlot]
    dropped: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(sum(s.own for s in self.shots), 3)

    def shot(self, shot_id: str) -> ShotSlot:
        return next(s for s in self.shots if s.shot_id == shot_id)


def build_timeline(plan: ScenePlan, narration: dict[int, float], vc: Any) -> Timeline:
    trans = dict(getattr(vc, "transitions", None) or {"cut": 0.04, "fade": 0.35, "fadeblack": 0.6, "flash": 0.25})
    beats: list[BeatSlot] = []
    shots: list[ShotSlot] = []
    dropped: list[str] = []
    t = 0.0
    for i, sc in enumerate(plan.scenes):
        t_in = trans.get(sc.transition, trans["cut"]) if i else 0.0
        pre = max(vc.first_pre_roll if i == 0 else vc.pre_roll, 0.5 * t_in)
        n = float(narration.get(sc.id, 0.0))
        post = vc.post_roll + float(sc.pause_after or 0.0)
        beat = BeatSlot(beat_id=sc.id, start=round(t, 3), pre=round(pre, 3), narration=round(n, 3), post=round(post, 3))
        all_shots = sc.all_shots()
        max_n = max(1, int(beat.duration // vc.min_shot_seconds))
        use = all_shots[:max_n]
        dropped += [sc.shot_id(k) for k in range(len(use), len(all_shots))]
        weights = [max(0.1, s.weight) for s in use]
        if len(use) > 1 and min(beat.duration * w / sum(weights) for w in weights) < vc.min_shot_seconds:
            weights = [1.0] * len(use)            # uneven weights would make a flicker shot: split evenly
        wsum = sum(weights)
        acc = 0.0
        for k, s in enumerate(use):
            own = beat.duration * weights[k] / wsum if k < len(use) - 1 else beat.duration - acc
            own = round(own, 3)
            shots.append(ShotSlot(beat_id=sc.id, k=k, shot_id=sc.shot_id(k), start=round(t + acc, 3), own=own))
            beat.shot_ids.append(sc.shot_id(k))
            acc += own
        beats.append(beat)
        t += beat.duration
    # transitions between consecutive shots
    beat_of = {b.beat_id: b for b in beats}
    scene_of = {sc.id: sc for sc in plan.scenes}
    for a, b in zip(shots, shots[1:]):
        kind = "cut" if a.beat_id == b.beat_id else scene_of[b.beat_id].transition
        d = trans.get(kind, trans["cut"])
        a.overlap = round(min(d, 0.5 * a.own, 0.5 * b.own), 3)
        a.transition_out = XFADE_NAME.get(kind, "fade")
    _ = beat_of
    return Timeline(beats=beats, shots=shots, dropped=dropped)
