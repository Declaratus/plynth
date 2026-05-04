"""Tests for plynth.cli._get_token, including the GHES_TOKEN deprecation path."""

from __future__ import annotations

import argparse
import warnings

import pytest

from plynth import cli


def _ns(token: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(token=token)


def test_get_token_uses_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("PLYNTH_TOKEN", raising=False)
    monkeypatch.delenv("GHES_TOKEN", raising=False)
    assert cli._get_token(_ns(token="from-flag")) == "from-flag"
    # 1.4 — passing the secret on the CLI should surface a stderr warning
    # so users notice the shell-history / process-listing exposure.
    assert "exposes the token" in capsys.readouterr().err


def test_get_token_flag_warning_suppressed_when_env_matches(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Redundant --token (same value as PLYNTH_TOKEN) is not worth warning about."""
    monkeypatch.setenv("PLYNTH_TOKEN", "same")
    monkeypatch.delenv("GHES_TOKEN", raising=False)
    assert cli._get_token(_ns(token="same")) == "same"
    assert "exposes the token" not in capsys.readouterr().err


def test_get_token_flag_warning_emitted_when_overriding_env(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If --token differs from PLYNTH_TOKEN, the flag is actively overriding — warn."""
    monkeypatch.setenv("PLYNTH_TOKEN", "from-env")
    monkeypatch.delenv("GHES_TOKEN", raising=False)
    assert cli._get_token(_ns(token="from-flag")) == "from-flag"
    assert "exposes the token" in capsys.readouterr().err


def test_get_token_reads_plynth_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("PLYNTH_TOKEN", "from-env")
    monkeypatch.delenv("GHES_TOKEN", raising=False)
    assert cli._get_token(_ns()) == "from-env"
    # Pure env-var path must not trigger the --token warning.
    assert "exposes the token" not in capsys.readouterr().err


def test_get_token_prefers_plynth_token_over_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When both are set, the new env var wins and we do not warn."""
    monkeypatch.setenv("PLYNTH_TOKEN", "new")
    monkeypatch.setenv("GHES_TOKEN", "old")
    # No DeprecationWarning should be emitted on the happy path.
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        token = cli._get_token(_ns())
    assert token == "new"
    assert not any(issubclass(w.category, DeprecationWarning) for w in captured)


def test_get_token_falls_back_to_ghes_token_with_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("PLYNTH_TOKEN", raising=False)
    monkeypatch.setenv("GHES_TOKEN", "legacy-tok")
    with pytest.warns(DeprecationWarning, match="GHES_TOKEN is deprecated"):
        token = cli._get_token(_ns())
    assert token == "legacy-tok"
    # The user also gets a stderr note (DeprecationWarning is silent in CLIs).
    assert "GHES_TOKEN is deprecated" in capsys.readouterr().err


def test_get_token_exits_when_nothing_set(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("PLYNTH_TOKEN", raising=False)
    monkeypatch.delenv("GHES_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        cli._get_token(_ns())
    assert exc_info.value.code == 1
    assert "PLYNTH_TOKEN" in capsys.readouterr().err
