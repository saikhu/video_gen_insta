from pathlib import Path

import pytest

from vgi.backends.image.mflux import _settle_output


def test_settle_output_moves_suffixed_file(tmp_path: Path):
    target = tmp_path / "scene_01_c0.png"
    (tmp_path / "scene_01_c0_1.png").write_bytes(b"x")
    assert _settle_output(target) == target and target.exists()
    assert not (tmp_path / "scene_01_c0_1.png").exists()


def test_settle_output_raises_when_nothing_written(tmp_path: Path):
    with pytest.raises(RuntimeError):
        _settle_output(tmp_path / "missing.png")
