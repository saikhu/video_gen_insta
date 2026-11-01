import json

from vgi.core.hashing import derive_seed
from vgi.core.job import Job
from vgi.media.ffmpeg import frames_for
from vgi.stages.video import scene_seconds


def test_frames_for_grid():
    assert frames_for(5.0, 25, 8) == 129       # 125 -> next 8k+1
    assert frames_for(1.0, 25, 8) == 25        # 25 is already 8*3+1
    assert frames_for(0.0, 25, 8) == 1
    assert (frames_for(7.3, 25, 8) - 1) % 8 == 0


def test_scene_seconds_tail_never_below_xfade():
    assert scene_seconds(4.0, 0.4, 0.5) == 4.9
    assert scene_seconds(4.0, 0.4, 0.1) == 4.8   # tail bumped to xfade


def test_seed_determinism():
    a = derive_seed(1, 3, 0, "video")
    assert a == derive_seed(1, 3, 0, "video")
    assert a != derive_seed(2, 3, 0, "video") and a != derive_seed(1, 4, 0, "video")


def test_job_states_and_plan_hash(project):
    job = Job.create(project / "outputs" / "jobs", "islamic_battles", "Battle of Badr", {"stages": {}})
    assert job.manifest.state == "created"
    job.scene_plan_path.write_text(json.dumps({"scenes": [{"id": 1, "keyframe_choice": 0}]}))
    job.approve()
    assert job.is_approved() and job.manifest.state == "approved"
    job.scene_plan_path.write_text(json.dumps({"scenes": [{"id": 1, "keyframe_choice": 2}]}))
    assert job.invalidate_if_plan_changed() is True
    assert job.manifest.state == "planned" and not job.is_approved()
    found = Job.find(project / "outputs" / "jobs", "badr")
    assert found.id == job.id
