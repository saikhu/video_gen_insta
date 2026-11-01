from vgi.config import ConfigLoader


def test_env_beats_stage_and_topic(project):
    cfg = ConfigLoader(project).load("mac_m5max", "islamic_battles")
    assert cfg.stages["video"]["backend"] == "remote_comfy"       # env overrides stages/video.yaml (stub)
    assert cfg.stages["keyframes"]["backend"] == "mflux"
    assert cfg.stages["music"]["engine"] == "none"
    assert cfg.stages["video"]["steps"] == 30                       # untouched stage key survives the deep merge


def test_topic_overrides_stage_but_not_env(project):
    cfg = ConfigLoader(project).load("linux_2x3090", "memes")
    assert cfg.stages["music"]["engine"] == "none"                  # env (none) beats topic (ace_step)
    assert cfg.stages["qa"]["face_check"] is True


def test_cli_override_and_content_excludes_env(project):
    cfg = ConfigLoader(project).load("mac_m5max", "islamic_battles", ["stages.video.steps=12", "global.seed_base=7"])
    assert cfg.stages["video"]["steps"] == 12
    assert cfg.global_.seed_base == 7
    content = cfg.content()
    assert "env" not in content and content["stages"]["video"]["steps"] == 12


def test_stage_schema_validation(project):
    import pytest

    with pytest.raises(Exception):
        ConfigLoader(project).load("mac_m5max", "islamic_battles", ["stages.video.steps=notanumber"])
