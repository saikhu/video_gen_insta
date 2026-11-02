"""--scene runs (beats) must leave other beats untouched, mark the stage partial, and --reseed must re-roll only
that beat's shots."""
import json

from vgi.config import ConfigLoader, config_from_content, load_yaml
from vgi.config.settings import Secrets
from vgi.core.job import Job
from vgi.core.runner import run_stages
from vgi.core.stage import RunContext


def _ctx(project, job, **kw):
    env_raw = load_yaml(project / "configs" / "env" / "mac_m5max.yaml")
    cfg = config_from_content(job.manifest.content_config, env_raw, {})
    return RunContext(root=project, job=job, cfg=cfg, secrets=Secrets(_env_file=None), dry_run=True, **kw)


def _beat(k):
    return k.split(".")[0]


def test_scene_filter_is_partial_then_merges(project):
    cfg = ConfigLoader(project).load("mac_m5max", "islamic_battles", ["stages.assemble.preset=ultrafast"])
    job = Job.create(project / "outputs" / "jobs", "islamic_battles", "Battle of Badr", cfg.content())
    run_stages(_ctx(project, job), ["research", "script"])
    run_stages(_ctx(project, job, scene_filter=[1], force=True), ["keyframes"])
    idx = json.loads((job.dir("keyframes") / "keyframes.json").read_text())
    assert {_beat(k) for k in idx} == {"1"} and job.record("keyframes").status == "partial"
    run_stages(_ctx(project, job), ["keyframes"])
    idx = json.loads((job.dir("keyframes") / "keyframes.json").read_text())
    plan = json.loads(job.scene_plan_path.read_text())
    n_shots = sum(len(s["shots"]) for s in plan["scenes"])
    assert len(idx) == n_shots and job.record("keyframes").status == "done"
    before = {k: v["seeds"] for k, v in idx.items()}
    run_stages(_ctx(project, job, scene_filter=[2], reseed=1, force=True), ["keyframes"])
    idx2 = json.loads((job.dir("keyframes") / "keyframes.json").read_text())
    assert all(idx2[k]["seeds"] != before[k] for k in idx2 if _beat(k) == "2")
    assert all(idx2[k]["seeds"] == before[k] for k in idx2 if _beat(k) != "2")
    assert json.loads((job.dir("keyframes") / "seeds.json").read_text()) == {"2": 1}


def test_video_scene_run_merges_clips(project):
    cfg = ConfigLoader(project).load("mac_m5max", "islamic_battles", ["stages.assemble.preset=ultrafast"])
    job = Job.create(project / "outputs" / "jobs", "islamic_battles", "Battle of Uhud", cfg.content())
    run_stages(_ctx(project, job), ["research", "script", "keyframes", "tts"])
    run_stages(_ctx(project, job, scene_filter=[3], force=True), ["video"])
    clips = json.loads((job.dir("video") / "clips.json").read_text())
    assert {c["beat_id"] for c in clips} == {3} and job.record("video").status == "partial"
    run_stages(_ctx(project, job), ["video"])
    clips = json.loads((job.dir("video") / "clips.json").read_text())
    assert sorted({c["beat_id"] for c in clips}) == list(range(1, 15))
