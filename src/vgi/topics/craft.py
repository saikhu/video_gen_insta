"""Storytelling craft shared by every topic: how a short vertical film holds attention.

Two passes: TREATMENT (free text, the writer thinks about drama) → STRUCTURE (JSON beats + shots).
Topic plugins add their own hard rules (depiction, honorifics, sources) on top.
"""
from __future__ import annotations

RETENTION = """\
CRAFT — write for a viewer who will swipe away in 1.5 seconds unless something grabs them:
1. COLD OPEN. The first line is the most arresting fact or image in the story, stated plainly, creating an open
   question (stakes, a number, a contradiction). No greetings, no "in this video", no "did you know".
2. STAKES EARLY. By the third beat the viewer knows who could lose what, and why it matters.
3. ESCALATION. Every beat raises tension or reveals something new. Use contrast (few against many), a ticking
   clock, a choice that could have gone the other way, a reversal.
4. THE TURN. One beat where everything hinges. Give it a short line and a held pause after it.
5. CLIMAX then RELEASE. Fast, short sentences in the action; slower, wider in the aftermath.
6. LAST LINE echoes the first: it closes the open question and leaves one memorable sentence.
VOICE: short sentences (4-14 words). Present tense for action is allowed. Concrete sensory detail (heat, dust,
water, the sound of hooves) instead of adjectives. No clichés ("little did they know", "epic", "legendary"),
no rhetorical questions in a row, no exclamation marks.
PICTURE: a new shot every 2-4 seconds. Alternate scale (aerial → wide → close-up object → silhouette), keep
light motivated and dramatic (dawn haze, hard noon, red dusk, torchlight), and give every shot ONE clear camera
move (slow push-in, crane up, low tracking, handheld drift, slow pull-back). Symbolic close-ups carry emotion:
an object, a texture, an animal, hands of an anonymous person, a banner in the wind.
SOUND: each shot names its diegetic sound (wind, hooves, crowd murmur at distance, water, cloth snapping).
"""

TREATMENT_TASK = """\
Write a TREATMENT for a {seconds_min:.0f}-{seconds_max:.0f} second vertical film.
Format (plain text):
LOGLINE: one sentence.
OPEN LOOP: the question the first line plants.
LENGTH: about {total_words} words of narration in total (that is the whole film); {beats_min}-{beats_max} beats.
BEATS: numbered. For each: the narration line(s) exactly as spoken ({words_max} words max per beat), then 1-{shots_max} shots as "- [shot type] picture | camera | sound",
and optionally TITLE: a 1-4 word on-screen title card (a place, a date, a number; at most {max_titles} in the whole film),
TRANSITION: cut (default for almost every beat) / fade / fadeblack (one act break) / flash (one impact),
PAUSE: seconds of silence after the line (ONLY the turn and the climax, 0.6-1.5; every other beat 0).
"""

STRUCTURE_TASK = """\
Convert the treatment into the JSON schema. Keep the narration EXACTLY as written in the treatment (fix only
spelling). One beat per numbered beat. shots: 1-{shots_max} per beat, in order; shot_type must be one of
{shots}. visual_prompt: one vivid English sentence for an image model (subject, setting, light, lens, distance),
never names of people. motion_prompt: the camera move. sound_prompt: diegetic sound only. on_screen_text: the
TITLE or "". transition: cut/fade/fadeblack/flash. pause_after: number of seconds (0 if none).
Total narration about {total_words} words.
"""


def total_words(sc) -> int:
    if getattr(sc, "total_words", 0):
        return int(sc.total_words)
    return int((sc.target_seconds_min + sc.target_seconds_max) / 2 * sc.words_per_second * 0.85)


def budget(sc) -> dict:
    return {"seconds_min": sc.target_seconds_min, "seconds_max": sc.target_seconds_max, "beats_min": sc.beats_min,
            "beats_max": sc.beats_max, "words_max": sc.beat_words_max, "shots_max": sc.shots_per_beat_max,
            "total_words": total_words(sc), "max_titles": sc.max_titles}
