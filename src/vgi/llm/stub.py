"""Stub LLM with canned-but-plausible outputs so Part A runs offline (dry runs, tests, no API key)."""
from __future__ import annotations

from ..core.models import (DraftBeat, DraftShot, FactSheet, Idea, IdeaPool, KeyFigure, NumberClaim, ScriptDraft, ScriptReview, SourceRef)
from .base import CitedResult, Doc, ParsedResult

STUB_SHOTS = ["aerial", "wide", "landscape", "silhouette", "crowd_distant", "map", "closeup_object", "wide"]


W = "desert wind, cloth flapping, sand hiss"


def _b(narr, shots, title="", tr="cut", pause=0.0):
    return DraftBeat(narration=narr, on_screen_text=title, transition=tr, pause_after=pause,
                     shots=[DraftShot(shot_type=t, visual_prompt=v, motion_prompt=m, sound_prompt=snd) for t, v, m, snd in shots])


BADR = [
    _b("Three hundred men. A thousand against them. One morning would decide whether a faith survived.", [
        ("aerial", "endless red dunes at first light, a thin line of tiny riders crossing a ridge, long shadows", "slow forward drift high above the dunes", W),
        ("closeup_object", "a sword hilt half buried in sand, grains blowing across the worn leather grip, golden backlight", "slow push-in", "wind, fine sand hissing over metal")],
       title="BADR · 624 CE"),
    _b("Spring, in the second year after the migration to Medina.", [
        ("map", "an antique parchment map of the Arabian peninsula, Mecca and Medina marked in ink, candlelight, shallow depth of field", "slow drift along the inked route", "candle flicker, paper rustle")],
       tr="fade"),
    _b("A Meccan caravan, heavy with goods, moved along the coast toward home.", [
        ("aerial", "a long camel caravan winding along a coastal desert track at golden hour, sea haze in the distance", "slow lateral tracking from high above", "camels grunting at distance, wind"),
        ("closeup_object", "camel hooves pressing into soft sand in slow motion, dust lifting in warm light", "low tracking shot beside the hooves", "heavy soft footfalls in sand")]),
    _b("Its leader sensed danger and sent a rider racing to Mecca.", [
        ("silhouette", "a lone rider on a galloping horse silhouetted against a huge low sun, dust trailing behind", "fast lateral tracking, slight handheld shake", "galloping hooves, rider breathing hard, wind"),
        ("wide", "a trail of dust stretching across an empty plain toward distant mountains", "slow crane up", W)]),
    _b("Mecca answered with an army. Early sources say close to a thousand men.", [
        ("crowd_distant", "a vast army seen from far away pouring out of a rocky canyon, banners and spears as a dark mass in the haze", "slow pull-back revealing the canyon", "thousands of distant footsteps, horses, murmuring crowd"),
        ("closeup_object", "a dark banner snapping violently in the wind against a pale sky", "handheld, slightly low angle", "banner cloth cracking in strong wind")],
       title="≈ 1,000 MEN"),
    _b("Against them stood about three hundred and thirteen, with only a few horses.", [
        ("silhouette", "a small group of figures silhouetted on a low ridge at dusk, only two horses among them, seen from behind", "slow push-in from behind the group", "quiet wind, a horse snorting"),
        ("closeup_object", "a worn leather water skin and a plain spear resting against a rock, last light", "static, gentle focus pull", "wind, distant insects")],
       title="313"),
    _b("Then the caravan slipped away. They could have turned back.", [
        ("landscape", "an empty coastal track at dusk, fresh caravan tracks fading into the sand, no one in sight", "slow pull-back", "wind, distant surf")],
       tr="fadeblack", pause=0.8),
    _b("They chose to stay.", [
        ("silhouette", "the small group standing still on the ridge as night falls, stars appearing above, seen from behind", "very slow push-in", "night wind, utter stillness")],
       pause=1.0),
    _b("They reached the wells of Badr first, and took the water.", [
        ("landscape", "a shallow sandy basin with low stone wells and a few palms at first light, a small camp of tents on the near ridge", "slow crane down toward the wells", "water dripping, morning birds, wind"),
        ("closeup_object", "a leather bucket rising out of a stone well, water spilling and glittering in the dawn sun", "slow motion, close tracking", "rope creaking, water splashing")],
       tr="fade"),
    _b("At dawn, three champions stepped forward from each side.", [
        ("silhouette", "two lines of distant silhouettes facing each other across open sand, three figures stepping out from each, huge sun behind", "slow push-in at ground level", "wind, sand crunching under slow footsteps"),
        ("closeup_object", "a hand tightening its grip on a sword handle, knuckles in hard backlight, face never visible", "extreme close-up, slow push-in", "leather creaking, a held breath")],
       tr="flash", pause=0.6),
    _b("The duels ended in moments. Then the lines met.", [
        ("crowd_distant", "two masses of fighters colliding in a storm of dust under the midday sun, seen from a high ridge, spears as abstract shapes", "handheld, slight push-in", "roar of a distant crowd, clashing metal, hooves"),
        ("closeup_object", "a shield falling into the sand, dust exploding around it in slow motion", "slow motion, low angle", "heavy thud, dust settling"),
        ("aerial", "dust clouds rolling across the valley of the wells, tiny figures inside them", "fast crane up and away", "muffled battle sound, wind")],
       tr="flash", pause=0.5),
    _b("By afternoon, the larger army broke, and ran.", [
        ("wide", "riders and running figures fleeing across a sun-bleached plain toward distant mountains, abandoned banners in the sand", "slow pull-back", "fading hooves, wind")]),
    _b("The Prophet Muhammad, peace be upon him, had led a small community through its first great test.", [
        ("landscape", "the wells of Badr at red dusk, an empty battlefield, smoke thinning in the air, a single banner standing", "very slow push-in", "evening wind, quiet")],
       tr="fade"),
    _b("Three hundred people refused to turn back. History turned with them.", [
        ("aerial", "the valley of Badr from very high at sunset, long shadows of the hills, the wells as tiny circles", "slow rising crane into the sky", "wind"),
        ("calligraphy", "an empty desert at golden hour with ornate Arabic geometric patterns glowing faintly in the sky as light", "slow drift upward", "soft wind")],
       title="17 RAMADAN · 2 AH", tr="fadeblack"),
]

PELICAN = [
    _b("This is Percival. Percival has a library book.", [
        ("character", "a dignified pelican in a tiny knitted vest holding a very old book in its beak, cozy town square, soft morning light", "slow push-in", "pigeons, distant traffic")],
       title="PERCIVAL"),
    _b("It is forty years overdue.", [
        ("closeup_object", "the book's stamped due date card reading 1986, dust on the pages", "snap zoom", "a single dramatic paper rustle")],
       pause=0.6),
    _b("The librarian is a lizard named Marla. Marla has waited.", [
        ("character", "a stern lizard librarian in tiny glasses behind a huge oak desk, stamps lined up perfectly", "slow push-in", "clock ticking, quiet library")]),
    _b("Percival offers payment.", [
        ("closeup_object", "a pelican beak gently placing a single shiny fish on the desk next to the stamp", "static, slow focus pull", "wet slap")],
       pause=0.8),
    _b("The library now accepts fish.", [
        ("wide", "a library counter with a handwritten sign that reads FISH ACCEPTED, a queue of hopeful birds holding fish", "slow pull-back to reveal the queue", "excited squawking")],
       tr="flash"),
]


class StubLLM:
    name = "stub"

    def generate(self, system: str, prompt: str, temperature: float | None = None) -> ParsedResult:
        beats = PELICAN if self.topic == "memes" else BADR
        lines = [f"LOGLINE: (stub) {self.subject}", "OPEN LOOP: (stub)", "BEATS:"]
        for i, b in enumerate(beats, 1):
            lines.append(f"{i}. {b.narration}" + (f"  TITLE: {b.on_screen_text}" if b.on_screen_text else ""))
            lines += [f"   - [{sh.shot_type}] {sh.visual_prompt} | {sh.motion_prompt} | {sh.sound_prompt}" for sh in b.shots]
        return ParsedResult(obj="\n".join(lines), model="stub")

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
        if schema is ScriptDraft:
            beats = PELICAN if self.topic == "memes" else BADR
            title = "Percival returns a book" if self.topic == "memes" else f"{self.subject}: the morning that decided everything"
            hook = beats[0].narration
            obj = ScriptDraft(title=title, hook=hook, beats=beats, cta="Follow for the next story.",
                              hashtags=["#IslamicHistory", "#Badr", "#Seerah"] if self.topic != "memes" else ["#funny", "#animals"],
                              sources_for_caption=["Wikipedia: Battle of Badr"] if self.topic != "memes" else [])
            return ParsedResult(obj=obj, model="stub")
        if schema is IdeaPool:
            ideas = [Idea(premise=f"A pelican tries to return a library book {i} years late", format="animal_skit",
                          characters=["Percival the pelican", "Marla the librarian lizard"],
                          punchline="The fine is paid in fish. The library now accepts fish.") for i in range(3)]
            return ParsedResult(obj=IdeaPool(ideas=ideas), model="stub")
        if schema is ScriptReview:
            return ParsedResult(obj=ScriptReview(issues=[]), model="stub")      # the canned script is pre-checked
        raise NotImplementedError(f"stub has no canned output for {schema}")
