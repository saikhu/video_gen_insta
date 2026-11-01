"""Stub backends: produce placeholder media so the whole DAG runs without models (dry runs, tests)."""
from __future__ import annotations

import math
import re
from pathlib import Path

from ..core.models import WordTiming
from ..media.ffmpeg import tone_wav
from ..media.images import placeholder_image


class StubImageBackend:
    name = "stub"

    def generate(self, prompt: str, negative: str, width: int, height: int, seed: int, out: Path, **_) -> Path:
        placeholder_image(out, width, height, f"[stub keyframe seed={seed}]\n{prompt}", seed)
        return out


class StubTTSBackend:
    name = "stub"

    def __init__(self, words_per_second: float = 2.5, sample_rate: int = 24000):
        self.wps = words_per_second
        self.sr = sample_rate

    def synthesize(self, text: str, out_wav: Path, **_) -> tuple[float, list[WordTiming]]:
        words = [w for w in re.split(r"\s+", text.strip()) if w]
        dur = max(1.0, len(words) / self.wps)
        tone_wav(out_wav, dur, self.sr)
        step = dur / max(1, len(words))
        timings = [WordTiming(word=w, start=round(i * step, 3), end=round((i + 1) * step - 0.02, 3))
                   for i, w in enumerate(words)]
        return dur, timings


def estimate_seconds(text: str, wps: float) -> float:
    n = len([w for w in re.split(r"\s+", text.strip()) if w])
    return math.ceil(n / wps * 10) / 10
