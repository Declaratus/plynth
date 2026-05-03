"""Tests for plynth.cli._resolve_state_dir (item 1.5)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from plynth import cli
from plynth.errors import ConfigError


def test_resolves_to_absolute_path(tmp_path: Path) -> None:
    resolved = cli._resolve_state_dir(str(tmp_path))
    assert resolved.is_absolute()
    assert resolved == tmp_path.resolve()


def test_dot_resolves_to_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli._resolve_state_dir(".") == tmp_path.resolve()


def test_rejects_when_path_is_a_regular_file(tmp_path: Path) -> None:
    f = tmp_path / "not-a-dir"
    f.write_text("hi")
    with pytest.raises(ConfigError, match="not a directory"):
        cli._resolve_state_dir(str(f))


def test_accepts_existing_writable_directory(tmp_path: Path) -> None:
    assert cli._resolve_state_dir(str(tmp_path)) == tmp_path.resolve()


def test_accepts_missing_path_when_parent_writable(tmp_path: Path) -> None:
    # Parent (tmp_path) exists and is writable; the missing leaf is allowed
    # through (the plan deliberately does not auto-mkdir, but does not reject
    # this case either — write-time failure is tolerated).
    missing = tmp_path / "does-not-exist-yet"
    assert cli._resolve_state_dir(str(missing)) == missing.resolve()


def test_rejects_missing_path_when_parent_missing(tmp_path: Path) -> None:
    # Parent itself does not exist, so there is no plausible recovery.
    deep_missing = tmp_path / "no-such-parent" / "leaf"
    with pytest.raises(ConfigError, match="not a writable directory"):
        cli._resolve_state_dir(str(deep_missing))


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: Windows os.access does not reliably reflect chmod bits.",
)
def test_rejects_unwritable_existing_directory(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)  # r-x, no write
    try:
        with pytest.raises(ConfigError, match="not writable"):
            cli._resolve_state_dir(str(locked))
    finally:
        locked.chmod(0o700)  # restore so pytest cleanup works


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: Windows os.access does not reliably reflect chmod bits.",
)
def test_rejects_missing_path_when_parent_unwritable(tmp_path: Path) -> None:
    parent = tmp_path / "ro-parent"
    parent.mkdir()
    parent.chmod(0o500)
    try:
        with pytest.raises(ConfigError, match="not a writable directory"):
            cli._resolve_state_dir(str(parent / "child"))
    finally:
        parent.chmod(0o700)


def test_does_not_mkdir(tmp_path: Path) -> None:
    """Resolution must not create directories on the filesystem."""
    target = tmp_path / "should-stay-missing"
    cli._resolve_state_dir(str(target))
    assert not target.exists()


def test_writability_uses_os_access(tmp_path: Path) -> None:
    """Writability is asserted via os.access; sanity-check both branches agree."""
    assert os.access(tmp_path, os.W_OK)
    cli._resolve_state_dir(str(tmp_path))
