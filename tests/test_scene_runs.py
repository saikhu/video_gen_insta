"""--scene runs must leave other scenes untouched, mark the stage partial, and --reseed must re-roll only that scene."""
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


def test_scene_filter_is_partial_then_merges(project):
    cfg = ConfigLoader(project).load("mac_m5max", "islamic_battles", ["stages.assemble.preset=ultrafast"])
    job = Job.create(project / "outputs" / "jobs", "islamic_battles", "Battle of Badr", cfg.content())
    run_stages(_ctx(project, job), ["research", "script"])
    run_stages(_ctx(project, job, scene_filter=[1], force=True), ["keyframes"])
    idx = json.loads((job.dir("keyframes") / "keyframes.json").read_text())
    assert list(idx) == ["1"] and job.record("keyframes").status == "partial"
    run_stages(_ctx(project, job), ["keyframes"])                      # partial → reruns, fills the rest
    idx = json.loads((job.dir("keyframes") / "keyframes.json").read_text())
    assert len(idx) == 8 and job.record("keyframes").status == "done"
    seeds_before = {k: v["seeds"] for k, v in idx.items()}
    # reseed scene 2 only
    run_stages(_ctx(project, job, scene_filter=[2], reseed=1, force=True), ["keyframes"])
    idx2 = json.loads((job.dir("keyframes") / "keyframes.json").read_text())
    assert idx2["2"]["seeds"] != seeds_before["2"]
    assert all(idx2[k]["seeds"] == seeds_before[k] for k in idx2 if k != "2")
    assert json.loads((job.dir("keyframes") / "seeds.json").read_text()) == {"2": 1}
    # a later full run keeps the reseeded scene (counters are persisted) and is a cache hit for every scene
    run_stages(_ctx(project, job, force=False), ["keyframes"])
    idx3 = json.loads((job.dir("keyframes") / "keyframes.json").read_text())
    assert idx3["2"]["seeds"] == idx2["2"]["seeds"]


def test_video_scene_run_merges_clips(project):
    cfg = ConfigLoader(project).load("mac_m5max", "islamic_battles", ["stages.assemble.preset=ultrafast"])
    job = Job.create(project / "outputs" / "jobs", "islamic_battles", "Battle of Uhud", cfg.content())
    run_stages(_ctx(project, job), ["research", "script", "keyframes", "tts"])
    run_stages(_ctx(project, job, scene_filter=[3], force=True), ["video"])
    clips = json.loads((job.dir("video") / "clips.json").read_text())
    assert [c["scene_id"] for c in clips] == [3] and job.record("video").status == "partial"
    run_stages(_ctx(project, job), ["video"])
    clips = json.loads((job.dir("video") / "clips.json").read_text())
    assert [c["scene_id"] for c in clips] == list(range(1, 9))
