import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A temp project root with the real configs copied in."""
    shutil.copytree(ROOT / "configs", tmp_path / "configs")
    (tmp_path / "outputs" / "jobs").mkdir(parents=True)
    (tmp_path / "data" / "corpus" / "islamic").mkdir(parents=True)
    (tmp_path / "comfy" / "workflows").mkdir(parents=True)
    return tmp_path
