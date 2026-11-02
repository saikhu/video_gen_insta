"""Serial story track (meerkat_story): chapter briefs, character appearance swap, romance rule, full dry run."""
import json
import shutil

import pytest
from conftest import ROOT
from test_dry_run import _ctx

from vgi.config import ConfigLoader
from vgi.core.job import Job
from vgi.core.models import Scene, ScenePlan, Shot
from vgi.core.runner import run_stages
from vgi.topics.serial_story import SerialStoryTopic, chapter_number

STORY = "docs/stories/where-the-burrows-lead"


@pytest.fixture()
def story_project(project):
    shutil.copytree(ROOT / STORY, project / STORY)
    return project


def _job(project, subject, overrides=None):
    cfg = ConfigLoader(project).load("mac_m5max", "meerkat_story", overrides or [])
    job = Job.create(project / "outputs" / "jobs", "meerkat_story", subject, cfg.content())
    return job, _ctx(project, job)


def test_chapter_number_forms():
    chapters = [{"number": i, "title": f"T{i}"} for i in range(1, 17)]
    assert chapter_number("3", chapters) == 3
    assert chapter_number("ch03", chapters) == 3
    assert chapter_number("Chapter 12", chapters) == 12
    assert chapter_number("t16", chapters) == 16
    with pytest.raises(ValueError):
        chapter_number("ch17", chapters)


def test_research_builds_chapter_brief(story_project):
    job, ctx = _job(story_project, "ch03")
    run_stages(ctx, ["research"])
    brief = (job.dir("research") / "chapter_brief.md").read_text()
    assert "chapter 3 of 16: After the Third Note" in brief
    assert "Nima notices that the sound ended in two stages" in brief          # CHAPTERS.md section body
    assert "Where has the basin water gone?" in brief                          # previous chapter's exit question
    assert "Door sleeves can connect existing passages" in brief               # fact established in chapter 1
    assert "## 4." not in brief                                                # no leak of the next chapter


def test_appearance_swap_is_idempotent(story_project):
    _, ctx = _job(story_project, "ch01")
    plugin = SerialStoryTopic()
    plan = ScenePlan(title="t", hook="h", scenes=[Scene(id=1, narration_text="Sera smiled at Tavi.", shots=[
        Shot(shot_type="two_shot", visual_prompt="Sera hands Tavi's pouch back to Tavi in the court."),
        Shot(shot_type="environment", visual_prompt="An empty sandstone court at noon.")])])
    assert plugin.expand_characters(ctx, plan) == 1
    vp = plan.scenes[0].shots[0].visual_prompt
    looks = ctx.cfg.topic.depiction["characters"]
    assert "Tavi" not in vp and "Sera" not in vp
    assert vp.startswith("The russet young female meerkat with the teal wrap hands")     # sentence start capitalised
    assert "the sandy-cream young male meerkat with the clay-red pouch's pouch" in vp
    assert vp.count(looks["tavi"]["look"]) == 1 and vp.count(looks["sera"]["look"]) == 1
    assert plan.scenes[0].narration_text == "Sera smiled at Tavi."                # the narrator still says names
    assert plugin.expand_characters(ctx, plan) == 0 and plan.scenes[0].shots[0].visual_prompt == vp


def test_kiss_only_in_romance_chapter(story_project):
    plugin = SerialStoryTopic()
    plan = ScenePlan(title="t", hook="h", scenes=[Scene(id=1, narration_text="They kissed.", shots=[
        Shot(shot_type="two_shot", visual_prompt="Two meerkats at dusk.")])])
    for subject, rejected in (("ch05", True), ("ch15", False)):
        _, ctx = _job(story_project, subject)
        run_stages(ctx, ["research"])
        errors, _ = plugin.validate(ctx, plan)
        assert any("kiss" in e for e in errors) is rejected, subject


def test_story_chapter_dry_run(story_project):
    job, ctx = _job(story_project, "ch01", ["stages.assemble.preset=ultrafast"])
    run_stages(ctx, ["research", "script", "keyframes", "storyboard"])
    assert job.manifest.state == "planned"
    plan = json.loads(job.scene_plan_path.read_text())
    prompts = [sh["visual_prompt"] for s in plan["scenes"] for sh in s["shots"]]
    assert not any("Tavi" in p or "Sera" in p for p in prompts)
    assert any("narrow dark break in the fur of his left brow" in p for p in prompts)
    job.approve()
    run_stages(ctx, ["tts", "video", "music", "captions", "assemble", "qa", "export"])
    assert job.manifest.state == "exported", job.record("qa").notes
    caption = (job.dir("export") / "caption.txt").read_text()
    assert "Where the Burrows Lead · Part 1/16: A Door Where There Wasn't One" in caption
