from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..core.models import ScenePlan, ScriptDraft
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
        """Returns (errors, warnings). Errors reject the plan; warnings show in the storyboard."""
        errors, warns = [], []
        sc = ctx.stage_cfg("script")
        whitelist = set(ctx.cfg.topic.depiction.get("shot_whitelist", []))
        wps = float(ctx.cfg.topic.narration.get("words_per_second", sc.words_per_second))
        n = len(plan.scenes)
        if n == 0:
            return ["plan has no beats"], []
        if not (sc.beats_min <= n <= sc.beats_max):
            warns.append(f"{n} beats, expected {sc.beats_min}-{sc.beats_max}")
        total = 0.0
        n_shots = sum(len(s.all_shots()) for s in plan.scenes)
        if n_shots / n < 1.4:
            warns.append(f"only {n_shots} shots for {n} beats (shots per beat {n_shots / n:.1f}); add second shots for faster cutting")
        for s in plan.scenes:
            words = len(s.narration_text.split())
            if not s.narration_text.strip():
                errors.append(f"beat {s.id}: empty narration")
            elif words > sc.beat_words_max * 1.5:
                errors.append(f"beat {s.id}: {words} words (max {sc.beat_words_max}); split it")
            elif words > sc.beat_words_max:
                warns.append(f"beat {s.id}: {words} words (max {sc.beat_words_max})")
            shots = s.all_shots()
            if len(shots) > sc.shots_per_beat_max:
                warns.append(f"beat {s.id}: {len(shots)} shots (max {sc.shots_per_beat_max}); extra shots may be dropped")
            for k, sh in enumerate(shots):
                if whitelist and sh.shot_type not in whitelist:
                    errors.append(f"shot {s.shot_id(k)}: shot_type {sh.shot_type!r} not in {sorted(whitelist)}")
                if not sh.visual_prompt.strip():
                    errors.append(f"shot {s.shot_id(k)}: empty visual_prompt")
            total += words / wps + 0.4 + s.pause_after
        if not (sc.target_seconds_min * 0.85 <= total <= sc.target_seconds_max * 1.15):
            warns.append(f"estimated length {total:.0f}s outside {sc.target_seconds_min:.0f}-{sc.target_seconds_max:.0f}s")
        return errors, warns

    # ---- review & repair (script stage loop) ----
    FIXABLE = ("honorific", "words (max", "shots per beat", "empty visual_prompt", "not in [", "estimated length",
               "beats, expected")

    def fixable(self, warns: list[str]) -> list[str]:
        return [w for w in warns if any(k in w for k in self.FIXABLE)]

    def autofix(self, ctx: RunContext, plan: ScenePlan) -> tuple[ScenePlan, list[str]]:
        """Mechanical fixes that should not depend on the model obeying: split beats over the word limit (at a
        sentence boundary, else the comma nearest the middle, else the middle), repeating until every beat fits.
        Shots are shared out; the first half keeps the title and transition, the second half keeps the pause."""
        limit = ctx.stage_cfg("script").beat_words_max
        notes: list[str] = []
        scenes = list(plan.scenes)
        for _ in range(12):
            out, changed = [], False
            for s in scenes:
                words = s.narration_text.split()
                if len(words) <= limit or len(words) < 4:
                    out.append(s)
                    continue
                a, b = _split_text(s.narration_text)
                shots = s.all_shots()
                sa = shots[: max(1, len(shots) // 2)]
                sb = shots[len(sa):] or [shots[-1].model_copy(
                    update={"motion_prompt": (shots[-1].motion_prompt + ", from a new angle").strip(", ")})]
                out.append(s.model_copy(update={"narration_text": a, "shots": sa, "pause_after": 0.0}))
                out.append(s.model_copy(update={"narration_text": b, "shots": sb, "on_screen_text": "", "transition": "cut"}))
                notes.append(f"split a {len(words)}-word beat")
                changed = True
            scenes = out
            if not changed:
                break
        for i, s in enumerate(scenes, start=1):
            s.id = i
        plan.scenes = scenes
        notes += self._pacing(ctx, plan)
        return plan, notes

    def _pacing(self, ctx: RunContext, plan: ScenePlan) -> list[str]:
        """Cap pauses, title cards and non-cut transitions so the edit keeps momentum."""
        sc = ctx.stage_cfg("script")
        notes = []
        max_p, cap = int(getattr(sc, "max_pauses", 3)), float(getattr(sc, "max_pause_seconds", 1.5))
        paused = [s for s in plan.scenes if s.pause_after > 0]
        n = len(plan.scenes)
        if len(paused) > max_p and len({s.pause_after for s in paused}) == 1 and n >= 4:
            # every beat got the same pause: no signal from the writer → classic positions (turn, climax, last line)
            slots = [round(0.55 * (n - 1)), round(0.8 * (n - 1)), n - 2][:max_p]
            keep = {plan.scenes[i].id for i in slots}
        else:
            ranked = sorted(paused, key=lambda s: (-s.pause_after, -s.id))      # ties → later beats
            keep = {s.id for s in ranked[:max_p]}
        for s in plan.scenes:
            new = min(cap, s.pause_after) if s.id in keep else 0.0
            if new != s.pause_after:
                notes.append(f"beat {s.id}: pause {s.pause_after}s -> {new}s")
                s.pause_after = new
        titles = [s for s in plan.scenes if s.on_screen_text.strip()]
        for s in titles[int(getattr(sc, "max_titles", 5)):]:
            notes.append(f"beat {s.id}: dropped title {s.on_screen_text!r}")
            s.on_screen_text = ""
        limits = dict(getattr(sc, "max_transitions", None) or {"fade": 3, "fadeblack": 2, "flash": 3})
        used: dict[str, int] = {}
        for s in plan.scenes[1:]:
            if s.transition == "cut":
                continue
            used[s.transition] = used.get(s.transition, 0) + 1
            if used[s.transition] > limits.get(s.transition, 0):
                notes.append(f"beat {s.id}: {s.transition} -> cut")
                s.transition = "cut"
        return notes

    OMISSION = re.compile(r"narration (does not|doesn't|should) (include|mention|specify|state|provide|note)|"
                          r"does not (include|mention)|doesn't (include|mention)|not mentioned|omit|"
                          r"missing (the )?(date|name|detail)|could (also )?include|should (also )?mention", re.I)

    def review(self, ctx: RunContext, llm, plan: ScenePlan, research: dict[str, Any]) -> tuple[list[str], float]:
        """Model-based review (e.g. fact check). Returns (issues, cost). Default: none."""
        return [], 0.0

    def structure_system(self, ctx: RunContext) -> str:
        return "You turn a film treatment into a structured shooting script."

    def repair(self, ctx: RunContext, llm, plan: ScenePlan, issues: list[str]) -> tuple[ScenePlan, float]:
        sc = ctx.stage_cfg("script")
        shots = ", ".join(ctx.cfg.topic.depiction.get("shot_whitelist", []))
        prompt = ("Here is a shooting script as JSON. Fix ONLY the problems listed, keep every other beat, line and shot "
                  "unchanged, and return the complete corrected script in the same schema.\n\n"
                  "PROBLEMS:\n- " + "\n- ".join(issues) +
                  f"\n\nConstraints: {sc.beats_min}-{sc.beats_max} beats, at most {sc.beat_words_max} words of narration per "
                  f"beat and {int(sc.target_seconds_max * sc.words_per_second)} words in total (fixing a problem must not make "
                  f"the script longer), "
                  f"beat, 1-{sc.shots_per_beat_max} shots per beat (use 2 shots in at least half the beats), shot_type one of "
                  f"{shots}, every visual_prompt a full sentence.\n\nSCRIPT:\n" + plan.to_draft().model_dump_json(indent=1))
        parsed = llm.parse(self.structure_system(ctx), prompt, ScriptDraft)
        return parsed.obj.to_plan(ctx.cfg.topic.music_policy), parsed.cost_usd

    def caption(self, ctx: RunContext, plan: ScenePlan, research: dict[str, Any]) -> str:
        t = ctx.cfg.topic
        parts = [plan.hook, "", plan.title]
        if plan.cta:
            parts += ["", plan.cta]
        srcs = list(dict.fromkeys(plan.sources_for_caption or research.get("source_titles", [])))
        if t.caption_footer:
            parts += ["", t.caption_footer.format(sources="; ".join(srcs) if srcs else "see pinned comment")]
        parts += ["", ctx.cfg.global_.ai_disclosure]
        return "\n".join(parts)


def _split_text(text: str) -> tuple[str, str]:
    parts = re.split(r"(?<=[.!?;])\s+", text.strip())
    if len(parts) >= 2:
        words_before = [len(" ".join(parts[: i + 1]).split()) for i in range(len(parts) - 1)]
        total = len(text.split())
        i = min(range(len(words_before)), key=lambda k: abs(words_before[k] - total / 2))
        return " ".join(parts[: i + 1]).strip(), " ".join(parts[i + 1:]).strip()
    words = text.split()
    mid = len(words) / 2
    conj = {"as", "and", "while", "when", "but", "until", "then", "so", "before", "after", "because", "where"}
    honorific = {"him,", "upon", "be", "peace"}            # never cut inside or right after "peace be upon him,"
    cands = [i + 1 for i, w in enumerate(words[:-1]) if w.endswith(",") and w.lower() not in honorific]
    cands += [i for i, w in enumerate(words) if w.lower() in conj and i > 0]
    cands = [c for c in cands if 4 <= c <= len(words) - 4]
    cut = min(cands, key=lambda c: abs(c - mid)) if cands else int(mid)
    return " ".join(words[:cut]).rstrip(","), " ".join(words[cut:])
