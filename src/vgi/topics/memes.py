from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from ..core.models import IdeaPool, ScenePlan, ScriptDraft
from ..core.stage import RunContext
from . import craft
from .base import TopicPlugin

IDEA_SYSTEM = """You invent ORIGINAL short comedic premises for AI-generated vertical videos.
Rules: original characters only (invent names and species), never existing memes, brands, celebrities, franchises or
copyrighted characters; no religion, ethnicity, disability, sexual content, politics or real tragedies.
Each idea: a one-sentence premise, a format id from {formats}, 1-3 characters, and the punchline."""

RULES = """\
HARD RULES: original characters only (invented names and species); never existing memes, brands, celebrities,
franchises or copyrighted characters; no religion, ethnicity, disability, sexual content, politics or tragedies.
Tone: {tone}. The punchline lands in the LAST beat; the beat before it is the setup and gets a short pause.
"""
TREATMENT_SYSTEM = "You write tiny comedic films for vertical video.\n\n" + craft.RETENTION + "\n" + RULES
STRUCTURE_SYSTEM = "You turn a comedic treatment into a structured shooting script.\n\n" + RULES


def _norm_tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z]{3,}", s.lower()))


def jaccard(a: str, b: str) -> float:
    ta, tb = _norm_tokens(a), _norm_tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


class MemesTopic(TopicPlugin):
    name = "memes"

    def _db(self, ctx: RunContext) -> sqlite3.Connection:
        p = ctx.root / ctx.cfg.topic.model_extra.get("originality", {}).get("jokes_db", "data/jokes_db.sqlite")
        p.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE IF NOT EXISTS jokes (premise TEXT PRIMARY KEY, job_id TEXT, used INTEGER DEFAULT 0)")
        return con

    def research(self, ctx: RunContext, llm) -> dict[str, Any]:
        t = ctx.cfg.topic
        orig = t.model_extra.get("originality", {}) if t.model_extra else {}
        formats = [f["id"] for f in (t.model_extra.get("formats", []) if t.model_extra else [])] or ["animal_skit"]
        rc = ctx.stage_cfg("research")
        parsed = llm.parse(IDEA_SYSTEM.format(formats=formats),
                           f"Generate {rc.ideas_per_run} ideas. Subject hint: {ctx.job.manifest.subject}", IdeaPool)
        pool: IdeaPool = parsed.obj
        banned = [b.lower() for b in orig.get("banned_characters", [])]
        con = self._db(ctx)
        known = [r[0] for r in con.execute("SELECT premise FROM jokes")]
        kept = []
        for idea in pool.ideas:
            text = f"{idea.premise} {' '.join(idea.characters)} {idea.punchline}".lower()
            if any(b in text for b in banned):
                continue
            sim = max((jaccard(idea.premise, k) for k in known), default=0.0)
            idea.originality_score = round(1 - sim, 3)
            if sim > float(orig.get("max_similarity", 0.6)):
                continue
            kept.append(idea)
        kept.sort(key=lambda i: -i.originality_score)
        out = ctx.job.dir("research") / "idea_pool.json"
        out.write_text(IdeaPool(ideas=kept).model_dump_json(indent=2), encoding="utf-8")
        chosen = kept[0] if kept else None
        if chosen is None:
            raise RuntimeError("no original idea survived the filters; rerun research")
        con.execute("INSERT OR IGNORE INTO jokes(premise, job_id, used) VALUES (?,?,0)", (chosen.premise, ctx.job.id))
        con.commit()
        return {"idea": chosen.model_dump(), "pool_size": len(kept), "artifacts": ["01_research/idea_pool.json"],
                "cost_usd": parsed.cost_usd, "source_titles": []}

    def script(self, ctx: RunContext, llm, research: dict[str, Any]) -> tuple[ScenePlan, float]:
        t, sc = ctx.cfg.topic, ctx.stage_cfg("script")
        rules = dict(tone=t.narration.get("tone", "deadpan"))
        ask = f"IDEA:\n{json.dumps(research['idea'], indent=1)}\n\n"
        cost, treatment = 0.0, ""
        if sc.treatment:
            tr = llm.generate(TREATMENT_SYSTEM.format(**rules), ask + craft.TREATMENT_TASK.format(**craft.budget(sc)),
                              temperature=sc.temperature)
            treatment, cost = str(tr.obj), cost + tr.cost_usd
            (ctx.job.dir("script") / "treatment.md").write_text(treatment, encoding="utf-8")
        structure = craft.STRUCTURE_TASK.format(shots=", ".join(t.depiction.get("shot_whitelist", [])), **craft.budget(sc))
        prompt = ask + (f"TREATMENT:\n{treatment}\n\n" if treatment else craft.RETENTION) + structure + \
            f"\nPick 5-8 hashtags from: {t.hashtags}. sources_for_caption: []."
        parsed = llm.parse(STRUCTURE_SYSTEM.format(**rules), prompt, ScriptDraft)
        return parsed.obj.to_plan(t.music_policy), cost + parsed.cost_usd

    def structure_system(self, ctx: RunContext) -> str:
        return STRUCTURE_SYSTEM.format(tone=ctx.cfg.topic.narration.get("tone", "deadpan"))

    def validate(self, ctx: RunContext, plan: ScenePlan) -> tuple[list[str], list[str]]:
        errors, warns = super().validate(ctx, plan)
        orig = ctx.cfg.topic.model_extra.get("originality", {}) if ctx.cfg.topic.model_extra else {}
        banned = [b.lower() for b in orig.get("banned_characters", [])]
        for s in plan.scenes:
            text = (s.narration_text + " " + " ".join(sh.visual_prompt for sh in s.all_shots())).lower()
            for b in banned:
                if b in text and not b.startswith("any "):
                    errors.append(f"scene {s.id}: banned character {b!r}")
        return errors, warns
