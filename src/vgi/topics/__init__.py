from .islamic_battles import IslamicBattlesTopic
from .memes import MemesTopic

PLUGINS = {p.name: p for p in (IslamicBattlesTopic, MemesTopic)}


def get_plugin(name: str):
    if name not in PLUGINS:
        raise KeyError(f"unknown topic plugin {name!r}; available: {sorted(PLUGINS)}")
    return PLUGINS[name]()
