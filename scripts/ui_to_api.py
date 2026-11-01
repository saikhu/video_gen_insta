#!/usr/bin/env python3
"""Convert a ComfyUI *UI-format* workflow (what the template browser / Save gives you) into *API format*
(what POST /prompt takes), then inject {{placeholders}} from a spec. Mirrors the frontend's graphToPrompt:

  python scripts/ui_to_api.py --object-info object_info.json --spec spec.json in.json out.json

object_info.json is `GET /object_info` from a running ComfyUI (any machine; CPU is fine).
spec.json: {"set": [{"class_type": "CLIPTextEncode", "title_contains": "Positive", "inputs": {"text": "{{prompt}}"}},
                    {"class_type": "KSampler", "inputs": {"seed": "{{seed}}", "steps": "{{steps}}"}}, ...],
            "require": ["{{prompt}}", "{{seed}}"]}
Matching: class_type (required) + optional title_contains / nth (0-based among matches). Every `require`
placeholder must end up somewhere or the script fails, so a template can't silently ignore a parameter.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

VIRTUAL = {"Note", "MarkdownNote", "PrimitiveNode", "Reroute"}
WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}


def is_widget(defn: Any) -> bool:
    """Input definition -> True when the frontend renders it as a widget (consumes a widgets_values slot)."""
    if not isinstance(defn, (list, tuple)) or not defn:
        return False
    t = defn[0]
    if isinstance(t, list):          # COMBO given as a list of choices
        return True
    if isinstance(t, str) and t in WIDGET_TYPES:
        return True
    return False


def input_defs(info: dict[str, Any], class_type: str) -> list[tuple[str, Any]]:
    node = info.get(class_type)
    if node is None:
        raise SystemExit(f"node type {class_type!r} not in object_info (custom node missing?)")
    out: list[tuple[str, Any]] = []
    for section in ("required", "optional"):
        for name, defn in (node.get("input", {}).get(section) or {}).items():
            out.append((name, defn))
    return out


def convert(ui: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    nodes = {n["id"]: n for n in ui["nodes"]}
    links = {l[0]: l for l in ui.get("links", [])}       # id -> [id, from_node, from_slot, to_node, to_slot, type]

    def resolve_source(link_id: int) -> tuple[int, int]:
        """Follow Reroute chains back to a real node output."""
        seen = 0
        while True:
            l = links[link_id]
            src, slot = l[1], l[2]
            n = nodes[src]
            if n["type"] != "Reroute":
                return src, slot
            in_link = n["inputs"][0].get("link")
            if in_link is None:
                raise SystemExit(f"Reroute {src} has no input")
            link_id = in_link
            seen += 1
            if seen > 50:
                raise SystemExit("reroute loop")

    api: dict[str, Any] = {}
    for nid, n in nodes.items():
        if n["type"] in VIRTUAL or n.get("mode") == 2:   # skip notes/primitives/reroutes and muted nodes
            continue
        if n.get("mode") == 4:
            raise SystemExit(f"node {nid} ({n['type']}) is bypassed; un-bypass or remove it before converting")
        by_name = {i["name"]: i for i in n.get("inputs", [])}
        values = list(n.get("widgets_values") or [])
        vi = 0
        inputs: dict[str, Any] = {}
        for name, defn in input_defs(info, n["type"]):
            widget = is_widget(defn)
            opts = defn[1] if isinstance(defn, (list, tuple)) and len(defn) > 1 and isinstance(defn[1], dict) else {}
            val = None
            if widget and vi < len(values):
                val = values[vi]
                vi += 1
                if opts.get("control_after_generate") or name in ("seed", "noise_seed"):
                    if vi < len(values) and isinstance(values[vi], str) and values[vi] in ("fixed", "increment", "decrement", "randomize"):
                        vi += 1
            slot = by_name.get(name)
            if slot and slot.get("link") is not None:
                src, sslot = resolve_source(slot["link"])
                srcn = nodes[src]
                if srcn["type"] == "PrimitiveNode":
                    inputs[name] = (srcn.get("widgets_values") or [None])[0]
                else:
                    inputs[name] = [str(src), sslot]
            elif widget:
                inputs[name] = val
            # non-widget, unlinked optional input: omitted (frontend does the same)
        api[str(nid)] = {"class_type": n["type"], "inputs": inputs, "_meta": {"title": n.get("title") or n["type"]}}
    return api


def delete_nodes(api: dict[str, Any], ids: list[str]) -> None:
    """Remove nodes; PreviewAny nodes that pointed at them go too; anything else still referencing them is an error."""
    gone = set(ids)
    for nid in ids:
        api.pop(nid, None)
    changed = True
    while changed:
        changed = False
        for nid, node in list(api.items()):
            refs = [v for v in node["inputs"].values() if isinstance(v, list) and len(v) == 2 and str(v[0]) in gone]
            if refs:
                if node["class_type"] == "PreviewAny":
                    api.pop(nid)
                    gone.add(nid)
                    changed = True
                else:
                    raise SystemExit(f"node {nid} ({node['class_type']}) still references deleted node(s) {refs}")


def inject(api: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    used: set[str] = set()
    for rule in spec.get("set", []):
        matches = [(nid, node) for nid, node in api.items() if node["class_type"] == rule["class_type"]
                   and (rule.get("title_contains", "").lower() in node["_meta"]["title"].lower())]
        if not matches:
            raise SystemExit(f"no node matches {rule}")
        nth = rule.get("nth", 0)
        if nth >= len(matches):
            raise SystemExit(f"rule {rule} wants match #{nth} but only {len(matches)} found")
        nid, node = matches[nth]
        for k, v in rule["inputs"].items():
            if k not in node["inputs"] and not rule.get("allow_new"):
                raise SystemExit(f"node {nid} ({node['class_type']}) has no input {k!r}; inputs: {list(node['inputs'])}")
            node["inputs"][k] = v
            if isinstance(v, str) and v.startswith("{{"):
                used.add(v)
    missing = [p for p in spec.get("require", []) if p not in used]
    if missing:
        raise SystemExit(f"placeholders not placed: {missing}")
    delete_nodes(api, spec.get("delete", []))   # after `set`, so re-pointed inputs no longer reference deleted nodes
    return api


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--object-info", required=True)
    ap.add_argument("--spec")
    ap.add_argument("src")
    ap.add_argument("dst")
    a = ap.parse_args()
    info = json.loads(Path(a.object_info).read_text(encoding="utf-8"))
    ui = json.loads(Path(a.src).read_text(encoding="utf-8"))
    if "nodes" in ui:
        api = convert(ui, info)
    else:  # already API format (e.g. exported with the frontend's graphToPrompt)
        api = ui
        for nid, node in api.items():
            if node.get("class_type") not in info:
                raise SystemExit(f"node {nid}: type {node.get('class_type')!r} not in object_info")
    if a.spec:
        api = inject(api, json.loads(Path(a.spec).read_text(encoding="utf-8")))
    Path(a.dst).write_text(json.dumps(api, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{a.dst}: {len(api)} nodes; types: {sorted({n['class_type'] for n in api.values()})}", file=sys.stderr)


if __name__ == "__main__":
    main()
