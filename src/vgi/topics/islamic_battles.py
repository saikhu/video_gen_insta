from __future__ import annotations

import json
import re
from typing import Any

from ..core.models import FactSheet, ScenePlan
from ..core.stage import RunContext
from ..llm.base import Doc
from .base import TopicPlugin, corpus_chunks

RESEARCH_SYSTEM = """You are a careful historian of early Islam writing for a documentary team.
Use ONLY the provided documents. Every factual statement must be supported by a citation from them.
Where documents disagree or are silent, say so explicitly under 'Uncertain points'. Never invent numbers.
Write in a neutral, respectful register; use 'Prophet Muhammad (peace be upon him)' on first mention."""

RESEARCH_QUESTION = """Produce a fact sheet for: {subject}.
Sections (markdown): Date and context; Location; Belligerents and commanders; Numbers (with source and confidence);
Timeline of the engagement (5-9 bullet steps); Outcome; Significance; Uncertain or disputed points; Sources used.
Keep it under 700 words."""

EXTRACT_SYSTEM = "Convert the fact sheet into the requested JSON exactly. Mark every prophet, member of the Prophet's household and every named Companion as depiction='forbidden'."

SCRIPT_SYSTEM = """You write narration for short vertical documentary videos (Instagram Reels) about early Islamic history.
Hard rules:
- Use only facts from the fact sheet. Hedge numbers with phrases like {hedges}.
- Narration is spoken aloud by a text-to-speech voice: write full honorifics in words, e.g. 'the Prophet Muhammad, peace be upon him' and 'may Allah be pleased with him' after a Companion's name on first mention.
- Visual prompts must NEVER show the face or body of the Prophet, any prophet, his household or any named Companion. {depiction_rule}
- Allowed shot types: {shots}. Prefer aerial/wide/silhouette/map shots; show armies only at a distance.
- Tone: {tone}. No religious rulings, no sectarian framing, no jokes about sacred figures.
- Avoid: {avoid}.
- Each scene's narration should take between {smin} and {smax} seconds at {wps} words per second; {nmin}-{nmax} scenes; total 45-75 seconds. Start with a strong hook.
- visual_prompt: one English sentence for an image model (environment, light, camera, distance), no names of sacred figures.
- motion_prompt: short camera/motion note for a video model.
- on_screen_text: optional short overlay (<= 6 words) or empty."""


class IslamicBattlesTopic(TopicPlugin):
    name = "islamic_battles"

    def research(self, ctx: RunContext, llm) -> dict[str, Any]:
        rc = ctx.stage_cfg("research")
        subject = ctx.job.manifest.subject
        corpus_dir = ctx.root / ctx.cfg.topic.model_extra.get("corpus_dir", "data/corpus/islamic") \
            if ctx.cfg.topic.model_extra else ctx.root / "data/corpus/islamic"
        aliases_cfg = (ctx.cfg.topic.model_extra or {}).get("retrieval_aliases", {}) or {}
        aliases = next((v for k, v in aliases_cfg.items() if k.lower() == subject.lower()), [])
        docs: list[Doc] = corpus_chunks(corpus_dir, subject, rc.chunk_chars, rc.max_chunks, rc.min_chunk_score,
                                        extra_terms=aliases) if corpus_dir.exists() else []
        log = ctx.log.for_stage("research")
        if not docs:
            log.warn(f"no corpus chunks matched {subject!r} in {corpus_dir}; fact sheet will be uncited",
                     corpus_dir=str(corpus_dir))
        else:
            log.info(f"{len(docs)} corpus chunks selected", files=sorted({d.title for d in docs}))
        cited = llm.cited(RESEARCH_SYSTEM, docs, RESEARCH_QUESTION.format(subject=subject))
        out_dir = ctx.job.dir("research")
        md = cited.text + "\n\n## Sources\n" + "\n".join(
            f"[{s['n']}] {s['title']} ({s['license']}) {s['url']}".rstrip() for s in cited.sources)
        (out_dir / "fact_sheet.md").write_text(md, encoding="utf-8")
        parsed = llm.parse(EXTRACT_SYSTEM, f"Fact sheet:\n\n{cited.text}\n\nSubject: {subject}", FactSheet)
        fs: FactSheet = parsed.obj
        (out_dir / "fact_sheet.json").write_text(fs.model_dump_json(indent=2), encoding="utf-8")
        (out_dir / "sources.json").write_text(json.dumps(cited.sources, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"fact_sheet": fs.model_dump(), "source_titles": [s["title"] for s in cited.sources],
                "artifacts": ["01_research/fact_sheet.md", "01_research/fact_sheet.json", "01_research/sources.json"],
                "cost_usd": cited.cost_usd + parsed.cost_usd, "uncited": not docs}

    def script(self, ctx: RunContext, llm, research: dict[str, Any]) -> tuple[ScenePlan, float]:
        t, sc = ctx.cfg.topic, ctx.stage_cfg("script")
        nar = t.narration
        system = SCRIPT_SYSTEM.format(
            hedges=", ".join(f"'{h}'" for h in nar.get("attribution_phrases", ["According to early sources"])),
            depiction_rule=t.depiction.get("rule", ""), shots=", ".join(t.depiction.get("shot_whitelist", [])),
            tone=nar.get("tone", "documentary"), avoid=", ".join(nar.get("avoid", [])),
            smin=sc.scene_seconds_min, smax=sc.scene_seconds_max, wps=sc.words_per_second,
            nmin=sc.scenes_min, nmax=sc.scenes_max)
        prompt = (f"Subject: {ctx.job.manifest.subject}\n\nFact sheet (JSON):\n"
                  f"{json.dumps(research['fact_sheet'], ensure_ascii=False, indent=1)}\n\n"
                  f"Write the ScenePlan. music_policy must be '{t.music_policy}'. Include 5-8 hashtags from: {t.hashtags}.")
        parsed = llm.parse(system, prompt, ScenePlan)
        plan: ScenePlan = parsed.obj
        plan.music_policy = t.music_policy
        return plan, parsed.cost_usd

    def validate(self, ctx: RunContext, plan: ScenePlan) -> tuple[list[str], list[str]]:
        errors, warns = super().validate(ctx, plan)
        avoid = [a.lower() for a in ctx.cfg.topic.narration.get("avoid", [])]
        for s in plan.scenes:
            low = s.narration_text.lower()
            if re.search(r"\b(the prophet|muhammad)\b", low) and "peace be upon him" not in low:
                warns.append(f"scene {s.id}: mentions the Prophet without the spoken honorific")
            for a in avoid:
                if a in low:
                    errors.append(f"scene {s.id}: narration touches avoided topic {a!r}")
            vp = s.visual_prompt.lower()
            for name in ("muhammad", "prophet's face", "face of"):
                if name in vp:
                    errors.append(f"scene {s.id}: visual_prompt references a forbidden depiction ({name!r})")
        return errors, warns
