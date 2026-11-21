# Tool map

Which tool does each step of building and keeping a board, as of 2026-11-14. Update this when a gap below closes.

| Step | Tool | Notes |
|---|---|---|
| Write the board spec | `board-spec` skill | This skill. |
| Create a Project, project fields, milestones, issues, dependencies | plynth | From a template and instance config. Org Projects on GitHub.com can also get basic views (name, layout, filter) with `views[].create: true`. |
| Change an existing board (field values, item moves, body edits) | mendrik `apply` | From a reviewed changeset. Dry-run first. |
| Report drift on an existing board | mendrik `inspect` | Planned (Declaratus/mendrik#7). Until it ships, read the board with the GitHub Projects MCP or `gh api`. |
| Compare a live board with its spec | `board-reviewer` subagent | Read-only. Returns JSON findings. |
| Roll several boards up into a portfolio view per audience | eyrl | Reads mendrik inspection output. Only rolls up what each audience can read. |
| Read Projects, fields, items, views | GitHub Projects MCP (`projects_list`, `projects_get`) or `gh api graphql` | Also `list_issue_fields` and `list_issue_types` for org-level definitions. |
| Add items, set item field values, create or update views, post status updates | GitHub Projects MCP (`projects_write`) or `gh api` | Bulk updates take up to 50 items per call. |
| Set parents, sub-issues and relates-to links | GitHub MCP (`sub_issue_write`) or `gh api` | plynth does not set native hierarchy yet (Declaratus/plynth#71). |

## Web UI only

These have no API today. List them in the spec's build steps for a person:

- Auto-add workflows (one repo per workflow, cap by plan).
- Other built-in Project workflows (item closed, pull request merged, auto-archive).
- Issue field definitions at the org or personal account (creating, renaming, options).
- Turning on hierarchy in a view, and view group, sort and visible fields that plynth does not map yet.
- Project base role and invited people or teams, when not set through the org's own tooling.

## Gaps worth closing

Tracked as issues:

- Multi-select project fields in plynth templates: Declaratus/plynth#80.
- plynth preflight of org issue fields, so a template cannot create a project field that shadows one: Declaratus/plynth#81.
- mendrik `inspect` output that carries what the board reviewer needs (field scope by owner, each item's repo and parent, inherited Project membership): Declaratus/mendrik#22.
- Native hierarchy in plynth: Declaratus/plynth#71.
