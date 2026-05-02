"""Tests for plynth.engine.api_base.derive_api_roots."""

from __future__ import annotations

import pytest

from plynth.engine.api_base import derive_api_roots

GITHUB_COM = ("https://api.github.com/graphql", "https://api.github.com")
GHES_BASE = "https://ghes.example.com"
GHES_ROOTS = (f"{GHES_BASE}/api/graphql", f"{GHES_BASE}/api/v3")


@pytest.mark.parametrize(
    "target",
    ["", "github.com", "https://api.github.com"],
    ids=["empty", "shorthand", "https-api-github-com"],
)
def test_github_com_forms_resolve_identically(target: str) -> None:
    assert derive_api_roots(target) == GITHUB_COM


def test_ghes_target_resolves_to_api_v3_paths() -> None:
    assert derive_api_roots(GHES_BASE) == GHES_ROOTS


def test_trailing_slash_tolerated_on_ghes() -> None:
    """Cosmetic — the InstanceConfig validator strips slashes too, but
    `derive_api_roots` is called from other code paths so it must be
    robust on its own."""
    assert derive_api_roots(f"{GHES_BASE}/") == GHES_ROOTS


def test_trailing_slash_tolerated_on_github_com_shorthand() -> None:
    assert derive_api_roots("github.com/") == GITHUB_COM


@pytest.mark.parametrize(
    ("bad", "expected_in_message"),
    [
        ("https://github.com", "api.github.com"),
        ("http://github.com", "https"),
        ("http://ghes.example.com", "https"),
        ("api.github.com", "https"),
        ("github.example.com", "https"),
    ],
)
def test_invalid_targets_rejected_with_specific_message(bad: str, expected_in_message: str) -> None:
    with pytest.raises(ValueError) as exc_info:
        derive_api_roots(bad)
    msg = str(exc_info.value)
    # The message must name the offending input so the user can spot the typo.
    assert bad in msg
    assert expected_in_message in msg
