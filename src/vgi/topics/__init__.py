from .islamic_battles import IslamicBattlesTopic
from .memes import MemesTopic
from .serial_story import SerialStoryTopic

PLUGINS = {p.name: p for p in (IslamicBattlesTopic, MemesTopic, SerialStoryTopic)}


def get_plugin(name: str):
    if name not in PLUGINS:
        raise KeyError(f"unknown topic plugin {name!r}; available: {sorted(PLUGINS)}")
    return PLUGINS[name]()
