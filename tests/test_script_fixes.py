from types import SimpleNamespace

from vgi.core.models import Scene, ScenePlan, Shot
from vgi.topics.islamic_battles import IslamicBattlesTopic


def _ctx(limit=22):
    sc = SimpleNamespace(beat_words_max=limit)
    return SimpleNamespace(stage_cfg=lambda name: sc)


def test_honorific_inserted_then_long_beat_split_within_limit():
    long = ("The Prophet Muhammad gathers his followers at dawn near the wells of Badr as the enemy approaches "
            "from the north. They pray together in the cold.")
    plan = ScenePlan(title="t", hook="h", scenes=[
        Scene(id=1, narration_text=long, on_screen_text="BADR", transition="fade", pause_after=0.8,
              shots=[Shot(shot_type="wide", visual_prompt="a"), Shot(shot_type="aerial", visual_prompt="b")]),
        Scene(id=2, narration_text="Muhammad led them.", shots=[Shot(shot_type="map", visual_prompt="c")])])
    plan, notes = IslamicBattlesTopic().autofix(_ctx(), plan)
    ids = [s.id for s in plan.scenes]
    assert ids == list(range(1, len(ids) + 1)) and len(ids) >= 3
    assert all(len(s.narration_text.split()) <= 22 for s in plan.scenes)
    assert "Prophet Muhammad, peace be upon him," in plan.scenes[0].narration_text      # never cut after the honorific
    assert not plan.scenes[1].narration_text.lower().startswith("peace")
    assert plan.scenes[-1].narration_text == "Muhammad, peace be upon him, led them."
    first, last_of_split = plan.scenes[0], plan.scenes[-2]
    assert first.on_screen_text == "BADR" and first.transition == "fade" and first.pause_after == 0
    assert last_of_split.pause_after == 0.8 and last_of_split.transition == "cut"           # the pause moves to the end


def test_existing_honorific_and_possessive_untouched():
    plan = ScenePlan(title="t", hook="h", scenes=[
        Scene(id=1, narration_text="The Prophet Muhammad, peace be upon him, prayed.", shots=[Shot(shot_type="wide", visual_prompt="a")]),
        Scene(id=2, narration_text="Muhammad's camp slept.", shots=[Shot(shot_type="wide", visual_prompt="b")])])
    plan, notes = IslamicBattlesTopic().autofix(_ctx(), plan)
    assert plan.scenes[0].narration_text.count("peace be upon him") == 1
    assert plan.scenes[1].narration_text == "Muhammad's camp slept."          # left for the review/repair loop


def test_omission_complaints_are_ignored():
    pat = IslamicBattlesTopic.OMISSION
    assert pat.search("The narration does not include the date of March 9")
    assert not pat.search("Abu Jahl was not killed by Ali according to the fact sheet")


def test_pacing_caps_pauses_titles_and_transitions():
    sc = SimpleNamespace(beat_words_max=22, max_pauses=2, max_pause_seconds=1.5, max_titles=2,
                         max_transitions={"fade": 1, "fadeblack": 1, "flash": 1})
    ctx = SimpleNamespace(stage_cfg=lambda name: sc)
    scenes = [Scene(id=i, narration_text=f"Line {i}.", pause_after=2.0 if i in (2, 5, 7) else 0.0,
                    on_screen_text=f"T{i}" if i % 2 else "", transition="fade",
                    shots=[Shot(shot_type="wide", visual_prompt="x")]) for i in range(1, 9)]
    plan, notes = IslamicBattlesTopic().autofix(ctx, ScenePlan(title="t", hook="h", scenes=scenes))
    assert sum(1 for s in plan.scenes if s.pause_after > 0) == 2 and max(s.pause_after for s in plan.scenes) == 1.5
    assert sum(1 for s in plan.scenes if s.on_screen_text) == 2
    assert sum(1 for s in plan.scenes[1:] if s.transition == "fade") == 1


def test_omission_filter_new_wording():
    pat = IslamicBattlesTopic.OMISSION
    assert pat.search("The narration does not specify that the plan to raid the caravan is debated")
    assert not pat.search("The fact sheet does not support the date March 17")
