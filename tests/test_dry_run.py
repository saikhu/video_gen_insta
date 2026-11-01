"""End-to-end dry run with stub backends: every stage runs and produces a spec-compliant MP4."""
import json

from vgi.config import ConfigLoader, config_from_content, load_yaml
from vgi.config.settings import Secrets
from vgi.core.job import Job
from vgi.core.runner import run_stages
from vgi.core.stage import RunContext
from vgi.media.ffmpeg import stream_info


def _ctx(project, job, dry_run=True):
    env_raw = load_yaml(project / "configs" / "env" / "mac_m5max.yaml")
    cfg = config_from_content(job.manifest.content_config, env_raw, {})
    return RunContext(root=project, job=job, cfg=cfg, secrets=Secrets(_env_file=None), dry_run=dry_run)


def test_full_dry_run(project):
    cfg = ConfigLoader(project).load("mac_m5max", "islamic_battles", ["stages.assemble.preset=ultrafast"])
    job = Job.create(project / "outputs" / "jobs", "islamic_battles", "Battle of Badr", cfg.content())
    ctx = _ctx(project, job)
    run_stages(ctx, ["research", "script", "keyframes", "storyboard"])
    assert job.manifest.state == "planned"
    job.approve()
    run_stages(ctx, ["tts", "video", "music", "captions", "assemble", "qa", "export"])
    assert job.manifest.state == "exported", job.record("qa").notes
    info = stream_info(job.dir("export") / "final.mp4")
    assert (info["width"], info["height"]) == (1080, 1920) and info["vcodec"] == "h264" and info["acodec"] == "aac"
    meta = json.loads((job.dir("export") / "metadata.json").read_text())
    assert meta["ai_generated"] is True
    # cache: re-running plan stages is a no-op
    rec_hash = job.record("keyframes").inputs_hash
    run_stages(ctx, ["keyframes"])
    assert job.record("keyframes").inputs_hash == rec_hash


def test_keyframe_choice_does_not_invalidate_keyframes(project):
    cfg = ConfigLoader(project).load("mac_m5max", "islamic_battles")
    job = Job.create(project / "outputs" / "jobs", "islamic_battles", "Battle of Uhud", cfg.content())
    ctx = _ctx(project, job)
    run_stages(ctx, ["research", "script", "keyframes"])
    before = job.record("keyframes").inputs_hash
    plan = json.loads(job.scene_plan_path.read_text())
    plan["scenes"][0]["keyframe_choice"] = 2
    job.scene_plan_path.write_text(json.dumps(plan))
    from vgi.stages.keyframes import KeyframesStage
    assert KeyframesStage().inputs_hash(ctx) == before
