# Spec template

Copy this and fill it in. Delete sections that don't apply. Every field names its scope and every Project names its owner.

```markdown
# Board spec: <program name>

As of <date>. Plan: <Free | Team | Enterprise Cloud>. Build only what is listed here.

**Goal:** <one sentence>
**Audiences:** <who reads which board, and what each must never see>

## Projects

| Project | Owner (type) | Visibility | Holds | Never holds |
|---|---|---|---|---|
| <title> | <login> (org or user) | private or public | <repos or item kinds> | <rule the reviewer can check> |

- Reused or new: <which existing Project, and what gets cleaned up>

## Items

| Source | Destination repo | Arrives in Project by |
|---|---|---|
| <kind of work> | <repo> | auto-add (filter) or import or manual or tool |

- Auto-add workflows used: <n> of <cap for the plan>. Repos over the cap arrive by <how>.
- Existing items: imported by <query or tool>, since auto-add does not back-fill.

## Fields

| Field | Type | Scope | Why |
|---|---|---|---|
| Priority | single select | issue field (org) | default, shared across boards |
| Status | single select | project field (<project>) | board columns |
| <field> | <type> | issue field (<owner>) or project field (<project>) | <why this scope> |

- Issue fields used: <n> of 25 at <owner>.
- Fields that differ by owner: <none, or the rename that keeps them apart>.

## Issue types

- <Type>: <what it means>. Exists: yes or no. Fallback: <label>.

## Hierarchy

- Shape: <type> → <type> → <type>. Deepest path <n> of 8. Widest parent <n> of 100.
- Cross-repo or cross-org parents live in <repo>.
- Inheritance: <for each cross-boundary parent, what its children are in and who removes inherited membership>.

## Relations

- Blocked by: <rule, direction>.
- Relates to: <rule>.
- Across an audience boundary: <recorded where, or not at all>.

## Views

| Project | View | Layout | Filter / group / sort | Set by |
|---|---|---|---|---|
| <project> | <question-shaped name> | table, board or roadmap | <settings> | plynth or UI |
| <project> | Hierarchy | table, hierarchy on | <settings> | UI |

## Visibility

- Project-level data on each Project (draft items, field values, status updates, view names, description) is safe for: <audience>.
- <any rule about status updates or READMEs>

## Build steps

| Step | Tool | Web UI only |
|---|---|---|
| <step> | plynth, mendrik, GitHub Projects MCP, gh api or person | yes or no |

## Open decisions

1. <decision>: <options>. Recommended: <option>, because <reason>.
```
