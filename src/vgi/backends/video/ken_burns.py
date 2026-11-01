"""Ken Burns video backend: pan/zoom over the keyframe. Used as stub and as the degraded fallback."""
from __future__ import annotations

from pathlib import Path

from ...media.ffmpeg import ken_burns


class KenBurnsBackend:
    name = "ken_burns"

    def __init__(self, fps: int, width: int, height: int, zoom_start: float, zoom_end: float, pre_scale: float):
        self.fps, self.width, self.height = fps, width, height
        self.zoom_start, self.zoom_end, self.pre_scale = zoom_start, zoom_end, pre_scale

    def generate(self, keyframe: Path, out: Path, seconds: float, seed: int, **_) -> Path:
        ken_burns(keyframe, out, seconds, self.fps, self.width, self.height, self.zoom_start, self.zoom_end,
                  self.pre_scale, direction=seed % 4)
        return out
