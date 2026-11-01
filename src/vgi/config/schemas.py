"""Pydantic schemas for configuration. Extra keys are allowed so YAML can carry backend-specific knobs."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")


class ReelSpec(_Open):
    width: int = 1080
    height: int = 1920
    fps: int = 25
    min_seconds: float = 45
    max_seconds: float = 75
    loudness_lufs: float = -14
    true_peak_dbtp: float = -1
    video_codec: str = "libx264"
    video_bitrate_max_mbps: float = 25
    audio_bitrate_kbps: int = 128
    audio_sample_rate: int = 48000


class SafeZone(_Open):
    top_px: int = 250
    bottom_px: int = 420
    side_px: int = 60


class GlobalConfig(_Open):
    project_name: str = "video_gen_insta"
    outputs_dir: str = "outputs/jobs"
    data_dir: str = "data"
    seed_base: int = 1
    reel: ReelSpec = Field(default_factory=ReelSpec)
    safe_zone: SafeZone = Field(default_factory=SafeZone)
    ai_disclosure: str = "This video was created with AI-generated visuals and voice."


class ResearchCfg(_Open):
    backend: str = "stub"
    model: str = "claude-opus-5-5"
    effort: str = "high"
    max_tokens: int = 16000
    max_chunks: int = 24
    chunk_chars: int = 3000
    min_chunk_score: int = 1
    ideas_per_run: int = 20


class ScriptCfg(_Open):
    backend: str = "stub"
    model: str = "claude-opus-5-5"
    effort: str = "high"
    max_tokens: int = 16000
    scenes_min: int = 6
    scenes_max: int = 10
    scene_seconds_min: float = 4.0
    scene_seconds_max: float = 9.0
    max_clip_seconds: float = 10.0
    words_per_second: float = 2.5


class StoryboardCfg(_Open):
    template: str = "preview.html.j2"
    open_browser: bool = False


class KeyframesCfg(_Open):
    backend: str = "stub"
    model: str = "z_image_turbo"
    n_candidates: int = 3
    gen_width: int = 768
    gen_height: int = 1344
    steps: int = 8
    guidance: float = 2.0
    seed_offset: int = 1000
    workflow: str = "image_flux3_klein"


class KenBurnsCfg(_Open):
    zoom_start: float = 1.0
    zoom_end: float = 1.12
    pre_scale: float = 1.6


class VideoCfg(_Open):
    backend: str = "stub"
    model: str = "ltx25"
    mode: str = "i2v"
    base_width: int = 544
    base_height: int = 960
    upscale: int = 2
    steps: int = 30
    fps: int = 25
    frame_grid: int = 8
    max_clip_seconds: float = 10.0
    native_audio: bool = True
    n_candidates: int = 1
    xfade_seconds: float = 0.4
    tail_seconds: float = 0.5
    timeout_seconds: int = 1800
    retries: int = 1
    fallback: str = "ken_burns"
    ken_burns: KenBurnsCfg = Field(default_factory=KenBurnsCfg)
    workflow_i2v: str = "video_ltx25_i2v"
    workflow_flf2v: str = "video_ltx25_flf2v"


class TtsCfg(_Open):
    engine: str = "stub"
    voice: str = "narrator_en"
    speed: float = 1.0
    sample_rate: int = 24000
    lexicon: str = "configs/pronunciation/lexicon.yaml"
    device: str = "cpu"
    pause_between_sentences_ms: int = 250


class MusicCfg(_Open):
    engine: str = "none"
    bed_gain_db: float = -18
    duck_db: float = -12
    prompt: str = ""


class CaptionStyle(_Open):
    font: str = "Arial Black"
    size: int = 68
    primary_colour: str = "&H00FFFFFF"
    secondary_colour: str = "&H0000D7FF"
    outline_colour: str = "&H00000000"
    back_colour: str = "&H80000000"
    outline: int = 4
    shadow: int = 2
    bold: int = -1
    alignment: int = 2


class CaptionsCfg(_Open):
    timing_provider: str = "engine"
    words_per_group: int = 3
    style: CaptionStyle = Field(default_factory=CaptionStyle)
    pop_in_ms: int = 80


class AssembleCfg(_Open):
    transition: str = "fade"
    crf: int = 18
    preset: str = "slow"
    pix_fmt: str = "yuv420p"
    loudnorm_two_pass: bool = True
    lra: float = 11
    font_dirs: list[str] = Field(default_factory=list)


class QaCfg(_Open):
    spec_check: bool = True
    loudness_tolerance_lu: float = 1.0
    face_check: bool = False
    face_threshold: float = 0.18
    face_sample_fps: float = 2
    face_model: str = "models/face_detection_yunet_2023mar.onnx"
    pronunciation_check: bool = False


class ExportCfg(_Open):
    name_template: str = "{job_id}"
    cover_scene: int = 1
    caption_max_chars: int = 2200
    max_hashtags: int = 30


class PublishCfg(_Open):
    enabled: bool = False
    is_ai_generated: bool = True
    share_to_feed: bool = True
    trial_reel: bool = False
    r2_public_base_url: str = ""


STAGE_SCHEMAS: dict[str, type[BaseModel]] = {
    "research": ResearchCfg,
    "script": ScriptCfg,
    "storyboard": StoryboardCfg,
    "keyframes": KeyframesCfg,
    "video": VideoCfg,
    "tts": TtsCfg,
    "music": MusicCfg,
    "captions": CaptionsCfg,
    "assemble": AssembleCfg,
    "qa": QaCfg,
    "export": ExportCfg,
    "publish": PublishCfg,
}


class Honorific(_Open):
    trigger: str
    caption: str


class TopicCfg(_Open):
    name: str
    plugin: str
    language: str = "en"
    style: str = "cinematic_desert"
    voice: str = "narrator_en"
    music_policy: str = "none"
    subjects: list[str] = Field(default_factory=list)
    honorifics: list[Honorific] = Field(default_factory=list)
    depiction: dict[str, Any] = Field(default_factory=dict)
    narration: dict[str, Any] = Field(default_factory=dict)
    hashtags: list[str] = Field(default_factory=list)
    caption_footer: str = ""
    stages: dict[str, Any] = Field(default_factory=dict)


class ComfyCfg(_Open):
    endpoints: list[str] = Field(default_factory=list)
    remote_ssh_host: str = ""
    dual_instance: bool = False
    gpu_lease: bool = False
    models_dir: str = ""


class EnvCfg(_Open):
    name: str
    hardware: dict[str, Any] = Field(default_factory=dict)
    power_watts: float = 100
    electricity_krw_per_kwh: float = 215
    comfy: ComfyCfg = Field(default_factory=ComfyCfg)
    stages: dict[str, Any] = Field(default_factory=dict)


class MergedConfig(BaseModel):
    """Everything a run needs. `content()` is the part frozen into the job manifest (env excluded)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    global_: GlobalConfig
    stages: dict[str, dict[str, Any]]
    topic: TopicCfg
    env: EnvCfg
    style: dict[str, Any]
    voice: dict[str, Any]
    lexicon: dict[str, Any]
    pricing: dict[str, Any]
    overrides: list[str] = Field(default_factory=list)

    def stage(self, name: str) -> BaseModel:
        schema = STAGE_SCHEMAS[name]
        return schema.model_validate(self.stages.get(name, {}))

    def content(self) -> dict[str, Any]:
        return {
            "global": self.global_.model_dump(),
            "stages": self.stages,
            "topic": self.topic.model_dump(),
            "style": self.style,
            "voice": self.voice,
            "lexicon": self.lexicon,
            "overrides": self.overrides,
        }
