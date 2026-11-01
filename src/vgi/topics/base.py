from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..core.models import ScenePlan
from ..core.stage import RunContext
from ..llm.base import Doc

_STOP = {"the", "of", "battle", "expedition", "siege", "and", "al", "a", "an"}


def subject_terms(subject: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z']+", subject.lower()) if t not in _STOP and len(t) > 2]


def parse_header(text: str) -> tuple[dict[str, str], str]:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            meta = {}
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            return meta, text[end + 4:]
    return {}, text


def corpus_chunks(corpus_dir: Path, subject: str, chunk_chars: int, max_chunks: int, min_score: int,
                  extra_terms: list[str] | None = None) -> list[Doc]:
    terms = list(dict.fromkeys(subject_terms(subject) + [t.lower() for t in (extra_terms or []) if t]))
    scored: list[tuple[int, Doc]] = []
    for p in sorted(corpus_dir.glob("*")):
        if p.suffix.lower() not in (".md", ".txt") or p.name.lower() == "readme.md":
            continue
        meta, body = parse_header(p.read_text(encoding="utf-8", errors="ignore"))
        paras, buf, chunks = body.split("\n\n"), "", []
        for para in paras:
            if len(buf) + len(para) > chunk_chars and buf:
                chunks.append(buf)
                buf = ""
            buf += para + "\n\n"
        if buf.strip():
            chunks.append(buf)
        for i, ch in enumerate(chunks):
            low = ch.lower()
            score = sum(low.count(t) for t in terms)
            if score >= min_score:
                scored.append((score, Doc(id=f"{p.stem}#{i}", title=meta.get("title", p.stem), text=ch.strip(),
                                          license=meta.get("license", ""), url=meta.get("url", ""))))
    scored.sort(key=lambda s: -s[0])
    return [d for _, d in scored[:max_chunks]]


class TopicPlugin(ABC):
    name: str = ""

    @abstractmethod
    def research(self, ctx: RunContext, llm) -> dict[str, Any]: ...

    @abstractmethod
    def script(self, ctx: RunContext, llm, research: dict[str, Any]) -> tuple[ScenePlan, float]: ...

    def validate(self, ctx: RunContext, plan: ScenePlan) -> tuple[list[str], list[str]]:
        """Returns (errors, warnings)."""
        errors, warns = [], []
        sc = ctx.stage_cfg("script")
        reel = ctx.cfg.global_.reel
        whitelist = set(ctx.cfg.topic.depiction.get("shot_whitelist", []))
        n = len(plan.scenes)
        if not (sc.scenes_min <= n <= sc.scenes_max):
            warns.append(f"{n} scenes, expected {sc.scenes_min}-{sc.scenes_max}")
        total = 0.0
        for s in plan.scenes:
            if whitelist and s.shot_type not in whitelist:
                errors.append(f"scene {s.id}: shot_type {s.shot_type!r} not in whitelist {sorted(whitelist)}")
            if s.target_seconds > sc.max_clip_seconds:
                errors.append(f"scene {s.id}: target_seconds {s.target_seconds} > max_clip_seconds {sc.max_clip_seconds}")
            if not s.narration_text.strip():
                errors.append(f"scene {s.id}: empty narration")
            total += s.target_seconds
        if total < reel.min_seconds or total > reel.max_seconds:
            warns.append(f"total target {total:.1f}s outside reel range {reel.min_seconds}-{reel.max_seconds}s")
        return errors, warns

    def caption(self, ctx: RunContext, plan: ScenePlan, research: dict[str, Any]) -> str:
        t = ctx.cfg.topic
        parts = [plan.hook, "", plan.title]
        if plan.cta:
            parts += ["", plan.cta]
        srcs = plan.sources_for_caption or research.get("source_titles", [])
        if t.caption_footer:
            parts += ["", t.caption_footer.format(sources="; ".join(srcs) if srcs else "see pinned comment")]
        parts += ["", ctx.cfg.global_.ai_disclosure]
        return "\n".join(parts)
