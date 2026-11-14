import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/codex/board-spec"
ADAPTER = ROOT / "adapters/claude/.claude"
READ_ONLY_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "mcp__github__projects_list",
    "mcp__github__projects_get",
    "mcp__github__list_issue_fields",
    "mcp__github__list_issue_types",
    "mcp__github__issue_read",
    "mcp__github__search_issues",
}


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, f"{path}: no frontmatter"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def test_board_spec_skill_and_adapter_are_valid() -> None:
    assert frontmatter(SKILL / "SKILL.md")["name"] == "board-spec"
    for ref in ["board-rules.md", "spec-template.md", "example-spec.md", "tool-map.md"]:
        assert (SKILL / "references" / ref).exists(), ref
    assert "display_name" in (SKILL / "agents/openai.yaml").read_text(encoding="utf-8")
    assert frontmatter(ADAPTER / "skills/board-spec/SKILL.md")["name"] == "board-spec"
    assert "board-spec" in (ROOT / "adapters/claude/INSTALL.md").read_text(encoding="utf-8")


def test_board_reviewer_stays_read_only() -> None:
    fields = frontmatter(ADAPTER / "agents/board-reviewer.md")
    assert fields["name"] == "board-reviewer"
    tools = {t.strip() for t in fields["tools"].split(",")}
    assert tools <= READ_ONLY_TOOLS, tools - READ_ONLY_TOOLS


def _skill_files() -> list[Path]:
    paths = [p for p in SKILL.rglob("*") if p.is_file()]
    paths += [p for p in ADAPTER.rglob("*") if p.is_file()]
    paths.append(ROOT / "adapters/claude/INSTALL.md")
    return paths


def test_skill_files_carry_no_addresses_or_ids() -> None:
    ipv4 = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
    guid = r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
    banned = re.compile(f"{ipv4}|{guid}", re.IGNORECASE)
    for path in _skill_files():
        match = banned.search(path.read_text(encoding="utf-8"))
        assert match is None, f"{path}: {match.group(0)!r}"


def _local_denylist() -> list[str]:
    # Terms that must never be committed live outside git: a gitignored
    # .plynth-denylist (one term per line) or PLYNTH_DENYLIST (comma separated).
    terms = os.environ.get("PLYNTH_DENYLIST", "").split(",")
    local = ROOT / ".plynth-denylist"
    if local.exists():
        terms += local.read_text(encoding="utf-8").splitlines()
    return [t.strip() for t in terms if t.strip() and not t.lstrip().startswith("#")]


def test_skill_files_avoid_local_denylist() -> None:
    terms = _local_denylist()
    if not terms:
        pytest.skip("no local denylist (.plynth-denylist or PLYNTH_DENYLIST)")
    banned = re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
    for path in _skill_files():
        match = banned.search(path.read_text(encoding="utf-8"))
        # Don't echo the term: the point is that it never lands in logs either.
        assert match is None, f"{path}: matches a denylisted term"
