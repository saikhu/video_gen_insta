"""ASS karaoke caption builder."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..core.models import WordTiming


@dataclass
class GroupedWord:
    text: str
    start: float
    end: float


def _norm(w: str) -> str:
    return re.sub(r"[^\w']+", "", w.lower())


def merge_honorifics(words: list[WordTiming], honorifics: list[dict]) -> list[WordTiming]:
    """Replace a spoken honorific phrase (n words) by one token carrying the caption form, keeping timing."""
    if not honorifics:
        return list(words)
    triggers = [([_norm(t) for t in h["trigger"].split()], h["caption"]) for h in honorifics]
    out: list[WordTiming] = []
    i = 0
    norm = [_norm(w.word) for w in words]
    while i < len(words):
        matched = False
        for trig, cap in triggers:
            n = len(trig)
            if norm[i:i + n] == trig:
                out.append(WordTiming(word=cap, start=words[i].start, end=words[i + n - 1].end))
                i += n
                matched = True
                break
        if not matched:
            out.append(words[i])
            i += 1
    return out


def _ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(scene_words: list[tuple[float, list[WordTiming]]], *, width: int, height: int, style: dict,
              bottom_margin_px: int, side_margin_px: int, words_per_group: int, pop_in_ms: int,
              honorifics: list[dict] | None = None, min_hold: float = 0.35) -> str:
    """scene_words: [(absolute_offset_seconds, words)] -> ASS document string."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{style.get('font', 'Arial Black')},{style.get('size', 68)},{style.get('primary_colour', '&H00FFFFFF')},{style.get('secondary_colour', '&H0000D7FF')},{style.get('outline_colour', '&H00000000')},{style.get('back_colour', '&H80000000')},{style.get('bold', -1)},0,0,0,100,100,0,0,1,{style.get('outline', 4)},{style.get('shadow', 2)},{style.get('alignment', 2)},{side_margin_px},{side_margin_px},{bottom_margin_px},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines: list[str] = []
    for offset, words in scene_words:
        merged = merge_honorifics(words, honorifics or [])
        for g in range(0, len(merged), words_per_group):
            group = merged[g:g + words_per_group]
            start = offset + group[0].start
            end = max(offset + group[-1].end, start + min_hold)
            parts = []
            for j, w in enumerate(group):
                nxt = group[j + 1].start if j + 1 < len(group) else group[-1].end
                dur_cs = max(1, int(round((nxt - w.start) * 100)))
                parts.append(f"{{\\kf{dur_cs}}}{w.word}")
            text = f"{{\\fad({pop_in_ms},0)}}" + " ".join(parts)
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{text}")
    return header + "\n".join(lines) + "\n"
