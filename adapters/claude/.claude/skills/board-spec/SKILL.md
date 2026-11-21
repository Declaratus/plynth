---
name: board-spec
description: Turn one program or workstream into a short GitHub Projects board spec before anything is created or changed on GitHub. Use when someone asks to design, plan, restructure or migrate a GitHub Projects board, decide which Projects to have and who owns them, or map work from another tracker onto GitHub issues and Projects. Bootstrapping the spec is plynth; per-board changes are mendrik; the board-reviewer subagent checks a live board against the spec.
---

# Board spec

Full skill, rules, template, example and tool map: `skills/codex/board-spec/` in the plynth repo (`SKILL.md`, `references/board-rules.md`, `references/spec-template.md`, `references/example-spec.md`, `references/tool-map.md`). Read `board-rules.md` before writing a spec.

Core rules:

- Visibility decides ownership. Project-level data (draft items, project field values, status updates, view names, description) is readable by everyone who can read the Project, org owners and org apps included.
- One Project per audience boundary; per-repo and per-team boards are views.
- Shared fields are org-level issue fields (defaults Priority, Effort, Start date, Target date; 25 per org or account). Board columns and board-only lanes are project fields. Never the same name with different definitions at two owners.
- Sub-issues inherit the parent's Project and milestone. Never parent private work under an item on a broader board.
- Hierarchy limits: eight levels, 100 sub-issues per parent. Hierarchy view on in every Project with parents.
- Auto-add: one repo per workflow, cap per Project Free 1, Team 5, Enterprise Cloud 20, no back-fill.
- Relates to is GA; use it instead of labels or body links.
- Every field names its scope, every Project its owner, every open decision stays open.
- No client names, hosts, IPs, GUIDs or people's names.
