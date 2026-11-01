from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def hash_obj(obj: Any) -> str:
    data = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def derive_seed(seed_base: int, *parts: Any) -> int:
    data = json.dumps([seed_base, *parts], default=str).encode()
    return int.from_bytes(hashlib.sha256(data).digest()[:4], "big") & 0x7FFFFFFF
