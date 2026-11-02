"""Serial story track: one job per chapter of a developed story (docs/stories/<name>/story.yaml + CHAPTERS.md).

This is the narrated adaptation the pipeline can make today: a storyteller voice tells each chapter while the
pictures show the characters. Per-character dialogue voices and reference-image identity conditioning are not
supported yet (see the story's PRODUCTION.md), so identity consistency comes from text: the writer names the
characters in visual prompts and `autofix` replaces every name with the same fixed appearance sentence from the
topic config (`depiction.characters`), so every keyframe and clip receives identical character descriptions.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..config.loader import load_yaml
from ..core.models import ScenePlan, ScriptDraft
from ..core.stage import RunContext
from . import craft
from .base import TopicPlugin

CRAFT = """\
CRAFT — this is one chapter of a continuing animated film, released as a vertical short:
1. OPEN ON ACTION. Begin inside the chapter's first moment: no recap, no "previously", no greeting.
2. ONE QUESTION. The chapter's question is felt in the first beats and answered (or sharpened) by the end.
3. CHARACTER FIRST. Show what each character wants through what they do: paws, ears, tails, posture, glances.
4. THE TURN. One beat where the chapter pivots; a short line and a held pause after it.
5. END ON THE EXIT QUESTION, so the last image can cut straight into the next chapter.
VOICE: a warm storyteller narrating in the past tense, close to the characters, short sentences (4-14 words),
concrete sensory detail. At most one short quoted line of dialogue per beat, taken from or close to the
chapter's voice sample, spoken by the narrator ("It wasn't here a minute ago," Tavi said.).
PICTURE: soft cinematic 3D animation. A new shot every 2-4 seconds; alternate wide geography, two-shots and
expressive close-ups; ONE clear camera move per shot; motivated light (warm court daylight, cool underground
water reflections, amber control light).
SOUND: each shot names its diegetic sound (wind, paws on sand or stone, rope, moving stone, water). No music.
"""

RULES = """\
HARD RULES (a script that breaks one is rejected):
- Stay inside THIS chapter: use only the events, facts and props in the brief; do not reveal later chapters.
- Characters on screen are exactly the cast listed in the brief. In every visual_prompt refer to each on-screen
  character by NAME ({names}); the pipeline replaces names with fixed appearance descriptions, so never describe
  their fur, markings or accessories yourself.
- They are animal-shaped meerkats (no clothing beyond their listed accessory, no human hands or bodies).
- {romance}
- Sound is diegetic only: no music, singing or instruments.
"""

TREATMENT_SYSTEM = "You are the head writer of an animated feature told as a series of short chapters.\n\n" + CRAFT + "\n" + RULES
STRUCTURE_SYSTEM = "You turn a chapter treatment into a structured shooting script.\n\n" + RULES

STRUCTURE_TASK = """\
Convert the treatment into the JSON schema. Keep the narration EXACTLY as written in the treatment (fix only
spelling). One beat per numbered beat. shots: 1-{shots_max} per beat, in order; shot_type must be one of
{shots}. visual_prompt: one vivid English sentence for an image model (who is in frame BY NAME, what they do,
setting, light, lens, distance). motion_prompt: the camera move. sound_prompt: diegetic sound only.
on_screen_text: "" except the first beat, which may carry the chapter title. transition: cut/fade/fadeblack/flash.
pause_after: seconds (0 if none). Total narration about {total_words} words.
"""

KISS = re.compile(r"\bkiss(es|ed|ing)?\b", re.IGNORECASE)
SENTENCE_START = re.compile(r"(^|[.!?]\s+)([a-z])")


def chapter_number(subject: str, chapters: list[dict[str, Any]]) -> int:
    """'3', 'ch03', 'Chapter 3' or a chapter title → chapter number."""
    s = subject.strip()
    m = re.fullmatch(r"(?:ch(?:apter)?[\s_-]*)?0*(\d+)", s, re.IGNORECASE)
    if m:
        n = int(m.group(1))
    else:
        n = next((c["number"] for c in chapters if c["title"].lower() == s.lower()), 0)
    if not any(c["number"] == n for c in chapters):
        raise ValueError(f"subject {subject!r} is not a chapter; use 1-{len(chapters)}, ch01 or a chapter title")
    return n


def md_section(text: str, heading_prefix: str) -> str:
    """Body of the first '## <heading_prefix>...' section, up to the next '## ' heading."""
    m = re.search(rf"^## {re.escape(heading_prefix)}.*?$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


class SerialStoryTopic(TopicPlugin):
    name = "serial_story"

    # ---- config helpers ----
    def _story_dir(self, ctx: RunContext) -> Path:
        extra = ctx.cfg.topic.model_extra or {}
        return ctx.root / extra.get("story_dir", extra.get("corpus_dir", ""))

    def _characters(self, ctx: RunContext) -> dict[str, dict[str, str]]:
        return dict(ctx.cfg.topic.depiction.get("characters", {}) or {})

    def _story(self, ctx: RunContext) -> dict[str, Any]:
        return load_yaml(self._story_dir(ctx) / "story.yaml")

    # ---- research: assemble the chapter brief from the story package ----
    def research(self, ctx: RunContext, llm) -> dict[str, Any]:
        d = self._story_dir(ctx)
        story = self._story(ctx)
        chapters = story["chapters"]
        n = chapter_number(ctx.job.manifest.subject, chapters)
        ch = next(c for c in chapters if c["number"] == n)
        prev = next((c for c in chapters if c["number"] == n - 1), None)
        md = (d / "CHAPTERS.md").read_text(encoding="utf-8")
        world = (d / "WORLD.md").read_text(encoding="utf-8") if (d / "WORLD.md").exists() else ""
        facts = story.get("facts", {})
        chars = self._characters(ctx)

        def fact_lines(ids):
            return [f"- {facts[f]['meaning']}" for f in ids if f in facts]

        lines = [f"# {story['title']} — chapter {n} of {len(chapters)}: {ch['title']}", "",
                 f"Target length: {ch['target_seconds']} s. Story day {ch.get('story_day')}, {ch.get('time_of_day', '')}.",
                 f"Dramatic movement: {ch.get('dramatic_movement', '')}",
                 f"Local payoff: {ch.get('local_payoff', '')}",
                 f"Exit question (end here): {ch.get('exit_question', '')}",
                 f"Locations: {', '.join(ch.get('locations', []))}", ""]
        if prev:
            lines += ["## Where the previous chapter ended",
                      f"Chapter {prev['number']} ({prev['title']}) paid off: {prev.get('local_payoff', '')}",
                      f"and left the question: {prev.get('exit_question', '')}", ""]
        else:
            lines += ["## This is the first chapter: introduce the place and the central duo through action.", ""]
        if ch.get("uses_established_facts"):
            lines += ["## Already known to the audience", *fact_lines(ch["uses_established_facts"]), ""]
        if ch.get("establishes_facts"):
            lines += ["## This chapter reveals", *fact_lines(ch["establishes_facts"]), ""]
        lines += ["## Chapter outline", md_section(md, f"{n}. ") or "(missing from CHAPTERS.md)", ""]
        lines += ["## Cast on screen"]
        for cid in ch.get("cast", []):
            c = chars.get(cid, {})
            lines.append(f"- {c.get('name', cid.title())}: {c.get('role', '')}".rstrip(": "))
        geo = md_section(world, "Stable geography")
        if geo:
            lines += ["", "## Geography (keep consistent)", geo]
        brief = "\n".join(lines).strip() + "\n"
        out = ctx.job.dir("research")
        (out / "chapter_brief.md").write_text(brief, encoding="utf-8")
        return {"chapter": n, "title": ch["title"], "story_title": story["title"], "chapters_total": len(chapters),
                "cast": ch.get("cast", []), "kiss_count": int(ch.get("kiss_count", 0) or 0), "brief": brief,
                "source_titles": [], "artifacts": ["01_research/chapter_brief.md"], "cost_usd": 0.0}

    # ---- script ----
    def _rules(self, ctx: RunContext, research: dict[str, Any]) -> dict[str, str]:
        chars = self._characters(ctx)
        names = ", ".join(chars.get(c, {}).get("name", c.title()) for c in research.get("cast", [])) or "the cast"
        romance = ("This chapter contains the film's one brief, mutual kiss, after safety; show it once, gently."
                   if research.get("kiss_count") else
                   "No kiss in this chapter; affection shows only through glances, care and small gestures.")
        return {"names": names, "romance": romance}

    def script(self, ctx: RunContext, llm, research: dict[str, Any]) -> tuple[ScenePlan, float]:
        t, sc = ctx.cfg.topic, ctx.stage_cfg("script")
        rules = self._rules(ctx, research)
        ask = f"CHAPTER BRIEF:\n{research['brief']}\n"
        cost, treatment = 0.0, ""
        if sc.treatment:
            tr = llm.generate(TREATMENT_SYSTEM.format(**rules), ask + craft.TREATMENT_TASK.format(**craft.budget(sc)),
                              temperature=sc.temperature)
            treatment, cost = str(tr.obj), cost + tr.cost_usd
            (ctx.job.dir("script") / "treatment.md").write_text(treatment, encoding="utf-8")
        structure = STRUCTURE_TASK.format(shots=", ".join(t.depiction.get("shot_whitelist", [])), **craft.budget(sc))
        prompt = ask + (f"TREATMENT:\n{treatment}\n\n" if treatment else CRAFT) + structure + \
            f"\nTitle: \"{research['title']}\". Pick 5-8 hashtags from: {t.hashtags}. sources_for_caption: []."
        parsed = llm.parse(STRUCTURE_SYSTEM.format(**rules), prompt, ScriptDraft)
        return parsed.obj.to_plan(t.music_policy), cost + parsed.cost_usd

    def structure_system(self, ctx: RunContext) -> str:
        research = self._research(ctx)
        return STRUCTURE_SYSTEM.format(**self._rules(ctx, research))

    def _research(self, ctx: RunContext) -> dict[str, Any]:
        p = ctx.job.dir("research") / "research.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    # ---- character identity: names → fixed appearance text ----
    def expand_characters(self, ctx: RunContext, plan: ScenePlan) -> int:
        """Replace character names in visual prompts with a short tag and append each on-screen character's fixed
        appearance once. Idempotent: prompts without names, or already carrying the appearance, are left alone."""
        chars = self._characters(ctx)
        changed = 0
        for s in plan.scenes:
            for sh in s.all_shots():
                text, present = sh.visual_prompt, []
                for cid, c in chars.items():
                    name = c.get("name", cid.title())
                    pat = re.compile(rf"\b{re.escape(name)}('s)?\b")
                    if pat.search(text):
                        tag = c.get("tag", f"the meerkat {name}")
                        text = pat.sub(lambda m, tag=tag: tag + ("'s" if m.group(1) else ""), text)
                        present.append(c)
                if present:   # a tag that replaced a sentence-initial name starts lowercase
                    text = SENTENCE_START.sub(lambda m: m.group(1) + m.group(2).upper(), text)
                appendix = [c["look"] for c in present if c.get("look") and c["look"] not in text]
                if appendix:
                    text = text.rstrip(". ") + ". " + " ".join(a.rstrip(".") + "." for a in appendix)
                if text != sh.visual_prompt:
                    sh.visual_prompt = text
                    changed += 1
        return changed

    def autofix(self, ctx: RunContext, plan: ScenePlan) -> tuple[ScenePlan, list[str]]:
        plan, notes = super().autofix(ctx, plan)
        n = self.expand_characters(ctx, plan)
        if n:
            notes.append(f"character appearance applied to {n} shot(s)")
        return plan, notes

    def validate(self, ctx: RunContext, plan: ScenePlan) -> tuple[list[str], list[str]]:
        errors, warns = super().validate(ctx, plan)
        research = self._research(ctx)
        if not research.get("kiss_count"):
            for s in plan.scenes:
                text = s.narration_text + " " + " ".join(sh.visual_prompt for sh in s.all_shots())
                if KISS.search(text):
                    errors.append(f"beat {s.id}: a kiss belongs only to the romance chapter; remove it")
        cast = set(research.get("cast", []))
        chars = self._characters(ctx)
        for cid, c in chars.items():
            if cid in cast or not c.get("tag"):
                continue
            if any(c["tag"] in sh.visual_prompt for s in plan.scenes for sh in s.all_shots()):
                warns.append(f"{c.get('name', cid)} appears on screen but is not in this chapter's cast")
        return errors, warns

    def caption(self, ctx: RunContext, plan: ScenePlan, research: dict[str, Any]) -> str:
        t = ctx.cfg.topic
        head = f"{research.get('story_title', '')} · Part {research.get('chapter', '?')}/{research.get('chapters_total', '?')}"
        parts = [plan.hook, "", f"{head}: {research.get('title') or plan.title}"]
        if t.caption_footer:
            parts += ["", t.caption_footer]
        parts += ["", ctx.cfg.global_.ai_disclosure]
        return "\n".join(parts)
