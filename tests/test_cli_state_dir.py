"""Tests for plynth.cli._resolve_state_dir (item 1.5).

Validation uses a write-and-delete probe rather than os.access so that
W_OK-without-X_OK on POSIX and ACL-governed writability on Windows are
both reflected. Negative-path tests that must construct an unwritable
directory remain POSIX-only because Path.chmod is effectively a no-op
for directories on Windows.
"""

from __future__ import annotations

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
    # Implicit behaviour test: the write-probe must succeed for this to pass.
    assert cli._resolve_state_dir(str(tmp_path)) == tmp_path.resolve()


def test_rejects_missing_directory_with_friendly_message(tmp_path: Path) -> None:
    """Per the tightened policy: any missing --state-dir is rejected up front."""
    missing = tmp_path / "does-not-exist"
    with pytest.raises(ConfigError, match="does not exist.*[Cc]reate"):
        cli._resolve_state_dir(str(missing))


def test_rejects_deeply_missing_path(tmp_path: Path) -> None:
    """Same rejection regardless of whether the parent exists."""
    deep_missing = tmp_path / "no-such-parent" / "leaf"
    with pytest.raises(ConfigError, match="does not exist"):
        cli._resolve_state_dir(str(deep_missing))


def test_does_not_mkdir(tmp_path: Path) -> None:
    """Validator must never create directories on the filesystem."""
    target = tmp_path / "should-stay-missing"
    with pytest.raises(ConfigError):
        cli._resolve_state_dir(str(target))
    assert not target.exists()


def test_probe_leaves_no_artifacts(tmp_path: Path) -> None:
    """The write-probe must clean up after itself (Copilot review #3)."""
    cli._resolve_state_dir(str(tmp_path))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: Path.chmod cannot reliably make a directory unwritable on Windows.",
)
def test_rejects_unwritable_existing_directory(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)  # r-x, no w
    try:
        with pytest.raises(ConfigError, match="not writable"):
            cli._resolve_state_dir(str(locked))
    finally:
        locked.chmod(0o700)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: the W_OK-without-X_OK gap can only be set up via chmod.",
)
def test_rejects_writable_but_unsearchable_directory(tmp_path: Path) -> None:
    """The exact case os.access misses: write bit set, but kernel rejects open()."""
    no_search = tmp_path / "no-search"
    no_search.mkdir()
    no_search.chmod(0o200)  # w only -- write bit set, no search/execute
    try:
        with pytest.raises(ConfigError, match="not writable"):
            cli._resolve_state_dir(str(no_search))
    finally:
        no_search.chmod(0o700)
