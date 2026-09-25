"""config.json can hold plaintext provider keys, so it must not be created
at the process umask."""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

from nanobot.config.loader import save_config
from nanobot.config.schema import Config

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX permission bits do not apply on Windows"
)


@posix_only
def test_new_config_is_private(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "config.json"

    save_config(Config(), path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


@posix_only
def test_existing_permissions_are_preserved(tmp_path: Path) -> None:
    """A user who deliberately widened or tightened the file keeps their choice."""
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o640)

    save_config(Config(), path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o640
