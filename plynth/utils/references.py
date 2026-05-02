"""Cross-reference resolution for Phase 5 body rewriting."""

from __future__ import annotations

import re


def resolve_crossrefs(
    body: str,
    ref_map: dict[str, str],
    skipped_refs: set[str] | None = None,
) -> str:
    """Replace {PREFIX}-### patterns in body text with #real_number or strikethrough.

    ref_map: {"{PREFIX}-001": "#47", "{PREFIX}-002": "#48", ...}
    skipped_refs: {"{PREFIX}-006", ...} — refs to mark as skipped

    Matching uses word-boundary-delimited patterns to avoid partial matches.
    """
    if skipped_refs is None:
        skipped_refs = set()

    all_refs = set(ref_map.keys()) | skipped_refs
    if not all_refs:
        return body

    # Sort longest first to avoid partial matches
    sorted_refs = sorted(all_refs, key=len, reverse=True)
    pattern = re.compile(
        r"(?<!\w)("
        + "|".join(re.escape(ref) for ref in sorted_refs)
        + r")(?!\w)"
    )

    def _replace(match: re.Match[str]) -> str:
        ref = match.group(1)
        if ref in skipped_refs:
            return f"~~{ref}~~ (skipped)"
        if ref in ref_map:
            return ref_map[ref]
        return ref

    return pattern.sub(_replace, body)
