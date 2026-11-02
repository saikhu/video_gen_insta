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
    beats_min: int = 10
    beats_max: int = 16
    shots_per_beat_max: int = 3
    beat_words_max: int = 22
    target_seconds_min: float = 55
    target_seconds_max: float = 85
    words_per_second: float = 2.5
    treatment: bool = True           # write a dramatic treatment first, then structure it
    total_words: int = 0             # narration budget; 0 = derive from target seconds
    max_pauses: int = 3
    max_pause_seconds: float = 1.5
    max_titles: int = 5
    max_transitions: dict[str, int] = Field(default_factory=lambda: {"fade": 3, "fadeblack": 2, "flash": 3})
    fact_check: bool = True
    repair_rounds: int = 2
    temperature: float = 0.8         # creative pass (local models)
    # legacy names kept so old configs still validate
    scenes_min: int = 6
    scenes_max: int = 16
    max_clip_seconds: float = 10.0


class StoryboardCfg(_Open):
    template: str = "preview.html.j2"
    open_browser: bool = False


class KeyframesCfg(_Open):
    backend: str = "stub"
    model: str = "z_image_turbo"
    n_candidates: int = 2
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
    # edit pacing (core/timeline.py)
    pre_roll: float = 0.12
    first_pre_roll: float = 0.3
    post_roll: float = 0.25
    min_shot_seconds: float = 1.6
    transitions: dict[str, float] = Field(default_factory=lambda: {"cut": 0.04, "fade": 0.35, "fadeblack": 0.6, "flash": 0.25})
    sound_in_prompt: bool = True     # append each shot's sound_prompt to the video prompt (LTX generates audio)
    audio_negative: str = ""         # appended to the video negative prompt (ignored by the distilled model at CFG 1)
    sound_style: str = "only natural on-location sound, like a field recording"   # opens the Sound: sentence


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
    bed_gain_db: float = -10         # bed level in gaps, vs the voice
    duck_db: float = -10             # extra attenuation under narration
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


class SoundCfg(_Open):
    """Sound design for the clips' own audio (media/sound.py). Levels in dB; *_db mix levels are relative to the voice."""
    demusic: bool = True              # strip sustained tones: LTX invents a score, and CFG 1 ignores negative prompts
    demusic_keep: float = 0.08        # fraction of the tonal part kept (1 = filter off)
    highpass_hz: float = 90           # cut the rumble that masks the voice
    min_content_s: float = 0.5        # a shot with less real sound is covered by its neighbours
    level_match: float = 0.75         # 0..1: how far each shot is pulled toward one level (1 = flat)
    max_boost_db: float = 12
    max_shortfall_db: float = 12      # a shot still this far under the others after boosting is left to its neighbours
    xfade_s: float = 0.5              # equal-power crossfade between neighbouring shots' sound
    jcut_s: float = 0.12              # the next shot's sound starts this much before its picture (J-cut)
    start_fade_s: float = 0.3
    end_fade_s: float = 1.5
    voice_db: float = -20             # narration level (RMS of the spoken parts, dBFS) before the final loudness pass
    diegetic_db: float = -15          # location sound under the voice
    diegetic_gap_db: float = -7       # location sound in gaps and dramatic pauses
    duck_attack_s: float = 0.25       # ramp down before a line starts
    duck_release_s: float = 0.6       # ramp back up after it ends
    presence_dip_db: float = -3       # carve ~2.8 kHz out of the beds so words stay clear
    room_tone: str = "wind"           # wind | none: continuous air under everything, never digital silence
    room_tone_db: float = -28


class AssembleCfg(_Open):
    transition: str = "fade"
    crf: int = 18
    preset: str = "slow"
    pix_fmt: str = "yuv420p"
    loudnorm_two_pass: bool = True
    lra: float = 11
    font_dirs: list[str] = Field(default_factory=list)
    sound: SoundCfg = Field(default_factory=SoundCfg)


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
    llm: dict[str, Any] = Field(default_factory=dict)
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
            "llm": self.llm,
            "overrides": self.overrides,
        }
