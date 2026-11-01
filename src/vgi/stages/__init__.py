from .assemble import AssembleStage
from .captions import CaptionsStage
from .export import ExportStage
from .keyframes import KeyframesStage
from .music import MusicStage
from .qa import QaStage
from .research import ResearchStage
from .script import ScriptStage
from .storyboard import StoryboardStage
from .tts import TtsStage
from .video import VideoStage

STAGE_CLASSES = {s.name: s for s in (ResearchStage, ScriptStage, KeyframesStage, StoryboardStage, TtsStage, VideoStage,
                                     MusicStage, CaptionsStage, AssembleStage, QaStage, ExportStage)}
