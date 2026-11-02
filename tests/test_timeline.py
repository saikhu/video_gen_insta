import pytest

from vgi.core.models import Scene, ScenePlan, Shot
from vgi.core.timeline import build_timeline


class VC:
    pre_roll = 0.12
    first_pre_roll = 0.3
    post_roll = 0.25
    min_shot_seconds = 1.6
    transitions = {"cut": 0.04, "fade": 0.35, "fadeblack": 0.6, "flash": 0.25}


def _plan():
    return ScenePlan(title="t", hook="h", scenes=[
        Scene(id=1, narration_text="a", shots=[Shot(shot_type="aerial", visual_prompt="x"), Shot(shot_type="wide", visual_prompt="y")]),
        Scene(id=2, narration_text="b", transition="fadeblack", pause_after=1.0, shots=[Shot(shot_type="map", visual_prompt="z")]),
        Scene(id=3, narration_text="c", transition="flash", shots=[Shot(shot_type="wide", visual_prompt="q") for _ in range(3)]),
    ])


def test_total_equals_sum_of_beats_and_shots_tile_the_reel():
    tl = build_timeline(_plan(), {1: 4.0, 2: 3.0, 3: 2.0}, VC)
    assert tl.total == pytest.approx(sum(b.duration for b in tl.beats))
    t = 0.0
    for s in tl.shots:                                  # shots start exactly where the previous one's own time ends
        assert s.start == pytest.approx(t, abs=1e-3)
        t += s.own
    assert tl.shots[-1].overlap == 0


def test_transitions_and_pauses():
    tl = build_timeline(_plan(), {1: 4.0, 2: 3.0, 3: 2.0}, VC)
    by = {s.shot_id: s for s in tl.shots}
    assert by["1.1"].transition_out == "fade" and by["1.1"].overlap == 0.04          # cut inside a beat
    assert by["1.2"].transition_out == "fadeblack" and by["1.2"].overlap == 0.6      # into beat 2
    assert by["2.1"].transition_out == "fadewhite"                                   # flash into beat 3
    b2 = tl.beats[1]
    assert b2.post == pytest.approx(0.25 + 1.0) and b2.pre >= 0.3                    # dramatic pause; pre covers fade
    assert b2.speech_start == pytest.approx(b2.start + b2.pre)


def test_short_beat_drops_extra_shots_and_even_split():
    tl = build_timeline(_plan(), {1: 4.0, 2: 3.0, 3: 2.0}, VC)
    assert tl.dropped == ["3.2", "3.3"]                 # 2.4 s beat cannot hold three 1.6 s shots
    plan = _plan()
    plan.scenes[0].shots[1].weight = 5.0                # would make shot 1.1 a flicker → even split instead
    tl2 = build_timeline(plan, {1: 3.0, 2: 3.0, 3: 2.0}, VC)
    a, b = tl2.shots[0], tl2.shots[1]
    assert a.own == pytest.approx(b.own, abs=0.01) and a.own >= VC.min_shot_seconds


def test_frames_on_ltx_grid():
    tl = build_timeline(_plan(), {1: 4.0, 2: 3.0, 3: 2.0}, VC)
    for s in tl.shots:
        f = s.frames(25, 8)
        assert (f - 1) % 8 == 0 and f / 25 >= s.length - 1e-6
