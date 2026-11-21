---
name: board-spec
description: Turn one program or workstream into a short GitHub Projects board spec before anything is created or changed on GitHub. Use when someone asks to design, plan, restructure or migrate a GitHub Projects board, decide which Projects to have and who owns them, map work from another tracker (Linear, Jira, Planner) onto GitHub issues and Projects, or choose fields, issue types, views, hierarchy and relations. Covers Project ownership (org or user), which items go where, org-level issue fields versus project fields, issue types, views including hierarchy, parent and sub-issue rules, relations and visibility. Bootstrapping the spec is plynth; per-board changes are mendrik; the board-reviewer subagent checks a live board against the spec.
---

# Board spec

A board spec is the contract between a program and its GitHub Projects. Whoever builds the board (plynth, mendrik, a script or a person in the web UI) follows it literally, and the board reviewer checks the live board against it, so anything not in the spec does not get created.

The boards this produces are shared planning surfaces. People filter them, export them and invite others to them. The spec has to get three things right: each item lives in exactly one obvious place, each field means one thing everywhere it appears, and nobody can see data they should not.

## Input

- A description of the program or workstream: its goal, the repos that own the work, the people and audiences who read the board, and any existing Projects.
- When migrating, the source tracker's structure (layers, fields, workflow states, relation kinds and counts).
- What the owning org's plan is (Free, Team, Enterprise Cloud). Auto-add caps depend on it.

If the program has no owning repos, or nobody can say who reads the board, stop and say so. Those are decisions, not spec details.

## Workflow

1. List the audiences and what each may see. Visibility decides ownership, so do this before anything else.
2. Pick the Projects: as few as possible, one per audience boundary. Name each owner (org or user) and say why.
3. Place items: which repos feed which Project, how items arrive (auto-add, query import, manual, tool), and which items must never appear where.
4. Fields: for each, decide org-level issue field or project field using [references/board-rules.md](references/board-rules.md). Read that file every time; the limits and dates matter.
5. Issue types, hierarchy (parent and sub-issue rules, depth, cross-repo and cross-org parents) and relations (blocked by, relates to).
6. Views: one per question a reader asks, including the hierarchy view.
7. Check the spec against the rules (limits, inheritance, visibility, plan caps) and fix it, don't annotate it.
8. Map each build step to its tool with [references/tool-map.md](references/tool-map.md), and list the web-UI-only steps as a checklist for a person.
9. List open decisions. Never write an open decision as settled.

## Output

Write the spec as Markdown in the working folder, named after the program. Use [references/spec-template.md](references/spec-template.md), and look at [references/example-spec.md](references/example-spec.md) for a filled-in one. Keep it to roughly two screens. If it runs long, the board will be confusing too.

Every field line says its scope (`issue field (org)` or `project field (<project>)`), and every Project line says its owner, so the reviewer can check drift without re-deriving the design.

## The rules that matter most

The full list is in the reference. These are the ones that get broken:

- **Visibility decides ownership.** Repo permissions protect issue content only. Project-level data (draft items, project field values, status updates, view names, the Project description) is readable by anyone who can read the Project, including org owners and org-installed apps. Work that must stay out of an org goes in a Project that org does not own.
- **Sub-issues inherit the parent's Project and milestone by default.** A child created under a parent on another board lands on the parent's board. Say for every cross-boundary parent what happens to its children, and never parent private work under an item on a broader board.
- **A field shared across repos and Projects is an org-level issue field, not a project field.** Priority, Effort, Start date and Target date exist as issue fields by default. Do not recreate them as project fields; same name, different definitions is drift by design.
- **Auto-add does not back-fill and has a per-project cap by plan.** Free allows 1 workflow, Team 5, Enterprise Cloud 20, one repo per workflow. Existing items need an import.
- **No client names, hosts, IPs, GUIDs or people's names** in the spec, in Project titles, view names, field options or descriptions. Use roles and generic names.

## Hand-off

The spec goes to building: plynth for a new board, mendrik for changes to an existing one, the GitHub Projects MCP or `gh api` for reads and item writes, and a person for the web-UI-only steps. After building, the `board-reviewer` subagent compares the live board with this spec and returns findings. A person takes the last look at visibility before the board is shared.
