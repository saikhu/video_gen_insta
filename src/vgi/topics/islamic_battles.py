from __future__ import annotations

import json
import re
from typing import Any

from ..core.models import FactSheet, ScenePlan, ScriptDraft, ScriptReview
from ..core.stage import RunContext
from ..llm.base import Doc
from . import craft
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

RULES = """\
HARD RULES (a script that breaks one is rejected):
- Facts only from the fact sheet. Hedge numbers and dates with phrases like {hedges}.
- Narration is spoken by a voice: write honorifics in full words: "the Prophet Muhammad, peace be upon him",
  and "may Allah be pleased with him" after a Companion's name on first mention.
- Pictures NEVER show the face or body of the Prophet, any prophet, his household or any named Companion.
  {depiction_rule} Armies and people appear at a distance, back-lit, as silhouettes, or from behind; close-ups
  are of objects, animals, landscape and anonymous hands only. Never name a person in a visual prompt.
- Sound is diegetic only: wind, hooves, footsteps, cloth, water, crowd at distance. NO music, singing, drums or
  any instrument.
- Tone: {tone}. No religious rulings, no sectarian framing, no jokes about sacred figures. Avoid: {avoid}.
"""

TREATMENT_SYSTEM = "You are the head writer of a respected history channel that makes short cinematic documentaries.\n\n" + craft.RETENTION + "\n" + RULES
STRUCTURE_SYSTEM = "You turn a film treatment into a structured shooting script.\n\n" + RULES


class IslamicBattlesTopic(TopicPlugin):
    name = "islamic_battles"

    def research(self, ctx: RunContext, llm) -> dict[str, Any]:
        rc = ctx.stage_cfg("research")
        subject = ctx.job.manifest.subject
        corpus_dir = ctx.root / ctx.cfg.topic.model_extra.get("corpus_dir", "data/corpus/islamic") \
            if ctx.cfg.topic.model_extra else ctx.root / "data/corpus/islamic"
        aliases_cfg = (ctx.cfg.topic.model_extra or {}).get("retrieval_aliases", {}) or {}
        aliases = next((v for k, v in aliases_cfg.items() if k.lower() == subject.lower()), [])
        max_chunks = rc.max_chunks
        if getattr(llm, "name", "") == "local":
            max_chunks = int((ctx.cfg.llm or {}).get("local", {}).get("research_max_chunks", 14))
        docs: list[Doc] = corpus_chunks(corpus_dir, subject, rc.chunk_chars, max_chunks, rc.min_chunk_score,
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
        return {"fact_sheet": fs.model_dump(), "source_titles": list(dict.fromkeys(s["title"] for s in cited.sources)),
                "artifacts": ["01_research/fact_sheet.md", "01_research/fact_sheet.json", "01_research/sources.json"],
                "cost_usd": cited.cost_usd + parsed.cost_usd, "uncited": not docs}

    def script(self, ctx: RunContext, llm, research: dict[str, Any]) -> tuple[ScenePlan, float]:
        t, sc = ctx.cfg.topic, ctx.stage_cfg("script")
        nar = t.narration
        rules = dict(hedges=", ".join(f"'{h}'" for h in nar.get("attribution_phrases", ["According to early sources"])),
                     depiction_rule=t.depiction.get("rule", ""), tone=nar.get("tone", "documentary"),
                     avoid=", ".join(nar.get("avoid", [])))
        facts = json.dumps(research["fact_sheet"], ensure_ascii=False, indent=1)
        ask = f"Subject: {ctx.job.manifest.subject}\n\nFACT SHEET (JSON):\n{facts}\n\n"
        cost = 0.0
        treatment = ""
        if sc.treatment:
            tr = llm.generate(TREATMENT_SYSTEM.format(**rules),
                              ask + craft.TREATMENT_TASK.format(**craft.budget(sc)), temperature=sc.temperature)
            treatment, cost = str(tr.obj), cost + tr.cost_usd
            (ctx.job.dir("script") / "treatment.md").write_text(treatment, encoding="utf-8")
        shots = ", ".join(t.depiction.get("shot_whitelist", []))
        structure = craft.STRUCTURE_TASK.format(shots=shots, **craft.budget(sc))
        prompt = ask + (f"TREATMENT:\n{treatment}\n\n" if treatment else craft.RETENTION + "\n") + structure + \
            f"\nPick 5-8 hashtags from: {t.hashtags}. sources_for_caption: short titles of the sources used."
        parsed = llm.parse(STRUCTURE_SYSTEM.format(**rules), prompt, ScriptDraft)
        plan = parsed.obj.to_plan(t.music_policy)
        return plan, cost + parsed.cost_usd

    def structure_system(self, ctx: RunContext) -> str:
        t = ctx.cfg.topic
        nar = t.narration
        return STRUCTURE_SYSTEM.format(
            hedges=", ".join(f"'{h}'" for h in nar.get("attribution_phrases", ["According to early sources"])),
            depiction_rule=t.depiction.get("rule", ""), tone=nar.get("tone", "documentary"), avoid=", ".join(nar.get("avoid", [])))

    def autofix(self, ctx: RunContext, plan: ScenePlan) -> tuple[ScenePlan, list[str]]:
        """Honorifics first (they add words), then the generic beat splitting."""
        notes: list[str] = []
        pat = re.compile(r"\b((?:the )?Prophet Muhammad|Muhammad)\b(?!['’]s)(?!,?\s*peace be upon him)", re.I)
        for s in plan.scenes:
            if "peace be upon him" in s.narration_text.lower():
                continue
            new, n = pat.subn(lambda m: f"{m.group(1)}, peace be upon him,", s.narration_text, count=1)
            if n:
                s.narration_text = re.sub(r",\s*([.!?])", r"\1", new)
                notes.append(f"beat {s.id}: added spoken honorific")
        plan, split_notes = super().autofix(ctx, plan)
        return plan, notes + split_notes

    def review(self, ctx: RunContext, llm, plan: ScenePlan, research: dict[str, Any]) -> tuple[list[str], float]:
        """Fact check: every narration line against the fact sheet (the creative pass can invent details)."""
        if not getattr(ctx.stage_cfg("script"), "fact_check", True):
            return [], 0.0
        lines = "\n".join(f"{s.id}. {s.narration_text}" for s in plan.scenes)
        facts = json.dumps(research["fact_sheet"], ensure_ascii=False, indent=1)
        prompt = (f"FACT SHEET:\n{facts}\n\nNARRATION (numbered beats):\n{lines}\n\n"
                  "List every problem, one issue per problem, with the beat number:\n"
                  "1. a claim (name, number, date, who did what) that the fact sheet does not support or contradicts;\n"
                  "2. a number or date stated as certain where the fact sheet is uncertain (it must be hedged);\n"
                  "3. the Prophet named without 'peace be upon him' spoken after his name, or a Companion named on first "
                  "mention without 'may Allah be pleased with him';\n"
                  "4. disrespectful or sectarian wording.\n"
                  "For each give a concrete fix (the corrected sentence, no longer than the original). Return an empty list "
                  "if there are no problems. Do NOT flag omissions: the film may leave out dates, names and details. Do not "
                  "flag style.")
        parsed = llm.parse("You are a careful fact checker for a history documentary.", prompt, ScriptReview)
        issues = [f"beat {i.beat}: {i.problem} -> {i.fix}" for i in parsed.obj.issues if not self.OMISSION.search(i.problem)]
        return issues, parsed.cost_usd

    def validate(self, ctx: RunContext, plan: ScenePlan) -> tuple[list[str], list[str]]:
        errors, warns = super().validate(ctx, plan)
        avoid = [a.lower() for a in ctx.cfg.topic.narration.get("avoid", [])]
        music = ("music", "song", "singing", "drum", "flute", "oud", "instrument", "choir", "nasheed", "orchestra")
        for s in plan.scenes:
            low = s.narration_text.lower()
            if re.search(r"\b(the prophet|muhammad)\b", low) and "peace be upon him" not in low:
                warns.append(f"beat {s.id}: mentions the Prophet without the spoken honorific")
            for a in avoid:
                if a in low:
                    errors.append(f"beat {s.id}: narration touches avoided topic {a!r}")
            for k, sh in enumerate(s.all_shots()):
                vp = sh.visual_prompt.lower()
                for name in ("muhammad", "prophet", "face of", "portrait of"):
                    if name in vp:
                        errors.append(f"shot {s.shot_id(k)}: visual_prompt references a forbidden depiction ({name!r})")
                if ctx.cfg.topic.music_policy == "native_only" and any(m in sh.sound_prompt.lower() for m in music):
                    errors.append(f"shot {s.shot_id(k)}: sound_prompt asks for music/instruments ({sh.sound_prompt!r})")
        return errors, warns
