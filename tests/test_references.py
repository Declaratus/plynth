from __future__ import annotations

from plynth.utils.references import resolve_crossrefs


def test_basic_substitution() -> None:
    body = "See {PREFIX}-001 and {PREFIX}-002."
    out = resolve_crossrefs(body, {"{PREFIX}-001": "#47", "{PREFIX}-002": "#48"})
    assert out == "See #47 and #48."


def test_skipped_ref_strikethrough() -> None:
    body = "See {PREFIX}-006."
    out = resolve_crossrefs(body, {}, skipped_refs={"{PREFIX}-006"})
    assert "~~{PREFIX}-006~~ (skipped)" in out


def test_unknown_ref_passthrough() -> None:
    body = "See {PREFIX}-999."
    out = resolve_crossrefs(body, {"{PREFIX}-001": "#47"})
    # {PREFIX}-999 is not in the map and not skipped — body is unchanged.
    assert "{PREFIX}-999" in out


def test_longest_first_avoids_partial_match() -> None:
    # {PREFIX}-1 must not greedily consume {PREFIX}-100.
    body = "{PREFIX}-100 and {PREFIX}-1"
    out = resolve_crossrefs(body, {"{PREFIX}-1": "#1", "{PREFIX}-100": "#100"})
    # Exact match: both refs must be resolved independently with no leftover
    # {PREFIX}-… text. A weak `"#1" in out` would pass even if only #100
    # were present (since "#1" is a substring of "#100"), so assert exact equality.
    assert out == "#100 and #1"
    assert "{PREFIX}" not in out


def test_empty_maps_no_change() -> None:
    body = "Plain text without refs."
    assert resolve_crossrefs(body, {}) == body


def test_word_boundary_protected() -> None:
    # An identifier-like context shouldn't match.
    body = "X{PREFIX}-001Y is not a ref."
    out = resolve_crossrefs(body, {"{PREFIX}-001": "#47"})
    assert "#47" not in out
