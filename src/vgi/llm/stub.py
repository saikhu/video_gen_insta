"""Stub LLM with canned-but-plausible outputs so Part A runs offline (dry runs, tests, no API key)."""
from __future__ import annotations

from ..core.models import FactSheet, Idea, IdeaPool, KeyFigure, NumberClaim, Scene, ScenePlan, SourceRef
from .base import CitedResult, Doc, ParsedResult

STUB_SHOTS = ["aerial", "wide", "landscape", "silhouette", "crowd_distant", "map", "closeup_object", "wide"]


class StubLLM:
    name = "stub"

    def __init__(self, subject: str = "Battle of Badr", topic: str = "islamic_battles"):
        self.subject, self.topic = subject, topic

    def cited(self, system: str, docs: list[Doc], question: str) -> CitedResult:
        srcs = [{"n": i + 1, "id": d.id, "title": d.title, "url": d.url, "license": d.license, "cited_text": ""}
                for i, d in enumerate(docs[:3])]
        marks = "".join(f"[{s['n']}]" for s in srcs)
        text = (f"# {self.subject} — fact sheet (STUB)\n\n"
                f"- Date: 17 Ramadan, 2 AH (March 624 CE) {marks}\n- Location: wells of Badr, Hejaz {marks}\n"
                f"- Belligerents: Muslims of Medina vs Quraysh of Mecca {marks}\n"
                f"- Numbers: early sources give roughly 313 vs about 1,000 (uncertain) {marks}\n"
                f"- Outcome: decisive Muslim victory {marks}\n")
        return CitedResult(text=text, sources=srcs, usage={}, cost_usd=0.0, model="stub")

    def parse(self, system: str, prompt: str, schema):  # type: ignore[override]
        if schema is FactSheet:
            obj = FactSheet(
                subject=self.subject, date="17 Ramadan 2 AH / 13 March 624 CE", location="Wells of Badr, Hejaz",
                belligerents=["Muslims of Medina", "Quraysh of Mecca"],
                numbers=[NumberClaim(claim="about 313 Muslims", source="early sira", confidence="medium"),
                         NumberClaim(claim="about 1,000 Quraysh", source="early sira", confidence="medium")],
                timeline=["Caravan of Abu Sufyan approaches", "Quraysh army marches from Mecca",
                          "Muslims secure the wells", "Duel of champions", "Main engagement and Quraysh rout"],
                key_figures=[KeyFigure(name="Prophet Muhammad", role="commander", depiction="forbidden"),
                             KeyFigure(name="Abu Jahl", role="Quraysh leader", depiction="forbidden")],
                outcome="Decisive Muslim victory", significance="First major battle of the Muslim community",
                uncertain_points=["exact troop numbers", "casualty counts"],
                sources=[SourceRef(id="stub", title="Stub source", license="n/a")])
            return ParsedResult(obj=obj, model="stub")
        if schema is ScenePlan:
            narr = [
                "In the second year after the migration to Medina, a caravan from Mecca changed the course of history.",
                "Quraysh of Mecca marched out with roughly a thousand men. According to early sources, the Muslims numbered about three hundred and thirteen.",
                "At the wells of Badr, the Muslims took position first, securing the water before the Quraysh arrived.",
                "The morning opened with single combat. Champions stepped forward from both lines.",
                "Then the lines met. Classical historians report fierce fighting through the heat of the day.",
                "By afternoon the Quraysh broke and fled toward Mecca, leaving their leaders on the field.",
                "The Prophet Muhammad, peace be upon him, led the community through its first great test.",
                "Badr became a turning point: a small community had faced its enemy and prevailed.",
            ]
            visuals = [
                ("aerial", "aerial view at dusk of a long camel caravan winding through red desert dunes toward the Hejaz, tiny figures, long shadows, dust haze",
                 "slow forward drift over the dunes"),
                ("wide", "a vast army of a thousand men seen from far away marching out of a rocky valley, banners and spears as a dark mass, haze and dust, no faces",
                 "slow lateral pan"),
                ("landscape", "the wells of Badr: a shallow sandy basin with low stone wells and sparse palms at first light, a small camp of tents on the near ridge, distant campfires",
                 "gentle push-in toward the wells"),
                ("silhouette", "two lone silhouetted warriors facing each other at sunrise across open sand, backlit by a huge low sun, heat shimmer, no visible faces",
                 "slow zoom toward the figures"),
                ("crowd_distant", "two lines of distant fighters colliding in a storm of dust under the midday sun, seen from a high ridge, spears and shields as abstract shapes",
                 "handheld tremor, dust drifting across frame"),
                ("wide", "the rout: scattered riders and running figures fleeing across a sun-bleached plain toward distant mountains, abandoned banners in the sand",
                 "slow pull-back"),
                ("calligraphy", "an empty desert camp at golden hour with a single tall banner in the wind, ornate Arabic geometric patterns faintly embossed in the sky as light",
                 "banner swaying, slow push-in"),
                ("map", "an antique parchment map of the Arabian peninsula with Mecca and Medina marked, a route traced in ink between them, candlelight, shallow depth of field",
                 "slow drift across the map"),
            ]
            scenes = [Scene(id=i + 1, shot_type=visuals[i % len(visuals)][0], narration_text=t,
                            target_seconds=round(max(4.0, min(9.0, len(t.split()) / 2.5 + 0.8)), 1),
                            visual_prompt=visuals[i % len(visuals)][1],
                            negative_prompt="close-up face, portrait, modern clothing, text",
                            motion_prompt=visuals[i % len(visuals)][2]) for i, t in enumerate(narr)]
            obj = ScenePlan(title=f"{self.subject}: the first great test", hook="313 against 1,000. One morning that changed history.",
                            scenes=scenes, music_policy="native_only", cta="Follow for more documented Islamic history.",
                            hashtags=["#IslamicHistory", "#Badr", "#Seerah"], sources_for_caption=["Stub source"])
            return ParsedResult(obj=obj, model="stub")
        if schema is IdeaPool:
            ideas = [Idea(premise=f"A pelican tries to return a library book {i} years late", format="animal_skit",
                          characters=["Percival the pelican", "Marla the librarian lizard"],
                          punchline="The fine is paid in fish. The library now accepts fish.") for i in range(3)]
            return ParsedResult(obj=IdeaPool(ideas=ideas), model="stub")
        raise NotImplementedError(f"stub has no canned output for {schema}")
