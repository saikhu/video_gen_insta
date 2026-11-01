"""Config loading with precedence: global < stages/<stage> < topics/<topic> < env/<env> < CLI overrides."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml

from .schemas import STAGE_SCHEMAS, EnvCfg, GlobalConfig, MergedConfig, TopicCfg


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    return data


def _parse_override(item: str) -> tuple[list[str], Any]:
    """'stages.video.steps=20' -> (['stages','video','steps'], 20). Values parsed as JSON when possible."""
    if "=" not in item:
        raise ValueError(f"override must look like key.path=value, got {item!r}")
    key, raw = item.split("=", 1)
    try:
        value: Any = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    return key.strip().split("."), value


def _apply_override(tree: dict[str, Any], path: list[str], value: Any) -> None:
    node = tree
    for p in path[:-1]:
        node = node.setdefault(p, {})
        if not isinstance(node, dict):
            raise ValueError(f"cannot override through non-mapping key {p!r}")
    node[path[-1]] = value


class ConfigLoader:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.cfg_dir = self.root / "configs"

    def available(self, kind: str) -> list[str]:
        d = self.cfg_dir / kind
        return sorted(p.stem for p in d.glob("*.yaml")) if d.exists() else []

    def load(self, env: str, topic: str, overrides: list[str] | None = None) -> MergedConfig:
        overrides = list(overrides or [])
        global_raw = load_yaml(self.cfg_dir / "global.yaml")
        stages: dict[str, dict[str, Any]] = {}
        for name in STAGE_SCHEMAS:
            p = self.cfg_dir / "stages" / f"{name}.yaml"
            stages[name] = load_yaml(p) if p.exists() else {}
        topic_raw = load_yaml(self.cfg_dir / "topics" / f"{topic}.yaml")
        env_raw = load_yaml(self.cfg_dir / "env" / f"{env}.yaml")

        # topic then env override stage keys through their `stages:` blocks (hardware wins)
        stages = deep_merge(stages, topic_raw.get("stages", {}))
        stages = deep_merge(stages, env_raw.get("stages", {}))

        tree: dict[str, Any] = {"global": global_raw, "stages": stages, "topic": topic_raw, "env": env_raw}
        for item in overrides:
            path, value = _parse_override(item)
            _apply_override(tree, path, value)

        topic_cfg = TopicCfg.model_validate(tree["topic"])
        style = self._load_optional("styles", topic_cfg.style)
        voice = self._load_optional("voices", topic_cfg.voice)
        lexicon_path = self.root / tree["stages"].get("tts", {}).get("lexicon", "configs/pronunciation/lexicon.yaml")
        lexicon = load_yaml(lexicon_path) if lexicon_path.exists() else {}
        pricing_path = self.cfg_dir / "pricing.yaml"
        pricing = load_yaml(pricing_path) if pricing_path.exists() else {}

        # validate every stage block against its schema (raises on bad types)
        for name, schema in STAGE_SCHEMAS.items():
            schema.model_validate(tree["stages"].get(name, {}))

        return MergedConfig(
            global_=GlobalConfig.model_validate(tree["global"]),
            stages=tree["stages"],
            topic=topic_cfg,
            env=EnvCfg.model_validate(tree["env"]),
            style=style,
            voice=voice,
            lexicon=lexicon,
            pricing=pricing,
            overrides=overrides,
        )

    def _load_optional(self, kind: str, name: str) -> dict[str, Any]:
        p = self.cfg_dir / kind / f"{name}.yaml"
        return load_yaml(p) if p.exists() else {}


def config_from_content(content: dict[str, Any], env_raw: dict[str, Any], pricing: dict[str, Any]) -> MergedConfig:
    """Rebuild a MergedConfig from a job's frozen content snapshot plus a (runtime) env."""
    stages = deep_merge(content["stages"], env_raw.get("stages", {}))
    return MergedConfig(
        global_=GlobalConfig.model_validate(content["global"]),
        stages=stages,
        topic=TopicCfg.model_validate(content["topic"]),
        env=EnvCfg.model_validate(env_raw),
        style=content.get("style", {}),
        voice=content.get("voice", {}),
        lexicon=content.get("lexicon", {}),
        pricing=pricing,
        overrides=content.get("overrides", []),
    )
