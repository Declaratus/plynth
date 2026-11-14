# Board rules

Platform facts below were captured on 2026-11-14 from GitHub's changelog and docs. Recheck anything dated before relying on it for a new design, and update this file when it changes.

## Platform facts

| Fact | Since |
|---|---|
| Issue fields are org-level. Defaults: Priority, Effort, Start date, Target date. Up to 25 per org. | GA for orgs 2026-07-02 |
| Issue fields on personal-account repos, up to 25 per account. | GA 2026-11-11 |
| Multi-select fields. | GA |
| "Relates to" links across REST, GraphQL, webhooks and search. | GA 2026-09-25 |
| Hierarchy view in Projects, on by default. | GA 2026-03-19 |
| Sub-issues can cross orgs. A new sub-issue inherits the parent's Project and milestone by default. | GA |
| 100 sub-issues per parent, eight levels deep. | Current limit |
| Auto-add: one repo per workflow. Cap per Project by plan: Free 1, Team 5, Enterprise Cloud 20. Applies to new and updated items only, no back-fill. | Current limit |
| A Project item is visible only to people who can read the item's repo. Others see a redacted item. | Current behaviour |

## Projects and ownership

- A Project is always owned by an org or a user. A "repo Project" is just an org or user Project linked to one repo.
- Default to one Project per audience boundary, with views per repo or team. A second Project is justified only by a different audience or a genuinely different workflow (its own status columns, iterations or fields that would clutter the first).
- Visibility decides ownership. Org owners and org-installed apps can read every Project in the org. If an audience must never see some work, that work goes in a Project owned somewhere the audience has no reach (another org or a user account), with its issues in a repo they cannot read.
- Say for each Project: owner, owner type (org or user), visibility (private or public), base role, who is invited, and the plan that sets its auto-add cap.
- Reuse an existing Project when it already holds the right items and has no conflicting fields. Say which, and what gets cleaned up.
- When a Project's repos live in other orgs, say who can read them and what a reader without access sees (redacted items, a broken tree). Do this even when the Project itself is still an open decision.

## Items

- Issues live in the repo that owns the work. A tracking-only repo is for cross-repo parents only, and must be no more visible than the most private child it holds.
- Say how items arrive in each Project: auto-add (with the filter and repo), query import for existing items, manual add, or a tool. Auto-add never back-fills, so any existing item needs an import step.
- If the auto-add cap is lower than the number of repos feeding a Project, say which repos are added another way.
- Draft items are project-level data with no repo behind them. Use them only for content every Project reader may see.
- Say which items must never appear in which Project, as a rule the reviewer can check ("no item from repo X in Project Y").

## Fields

Decide the scope of every field:

| Use an org-level issue field when | Use a project field when |
|---|---|
| The value belongs to the issue wherever it appears (priority, effort, dates, customer impact) | The value only means something on one board (board status column, iteration, triage lane) |
| More than one Project or repo filters or reports on it | It is a planning overlay one team owns |
| A rollup tool (eyrl) reads it across boards | It would confuse readers elsewhere |

- Priority, Effort, Start date and Target date are default issue fields. Use them, don't redefine them per Project.
- A Project still needs its own Status field for board columns. That is a project field.
- Never define the same field name with different types or options at two owners (org issue field versus project field, or two Projects). If two boards must differ, give the fields different names.
- Use multi-select when an item can genuinely hold several values (several initiatives). Do not fake it with a single-select plus labels.
- Remember the cap: 25 issue fields per org or account. Count them.
- Project field values are project-level data. A field whose values could name a client or private context does not belong on a Project the wrong audience can read.

## Issue types

- Issue types are org-level. Use them for kinds of work (Initiative, Epic, Task, Bug), not for status or area.
- Say which types the spec needs, whether they exist yet, and the fallback (a label) if they cannot be added.
- Personal accounts have no org issue types; a user-owned Project with user repos falls back to labels.

## Hierarchy

- Parent and sub-issue is for "part of". Use it for initiative → epic → issue.
- Depth limit is eight levels, 100 sub-issues per parent. Say the deepest path and the widest parent.
- Sub-issues inherit the parent's Project and milestone by default. For every parent whose children live in another repo, org or Project, say what the children should be in and who removes the inherited membership.
- Never parent private or client work under an item on a broader board. Inheritance will put it there, and the parent's title and the hierarchy view show it to the wrong audience.
- Cross-org sub-issues work, but each reader only sees what they can read. Say who sees a broken tree.
- Turn on the hierarchy view in every Project that holds parents. It is on by default; say so anyway so the reviewer checks it.

## Relations

- Blocked by / blocking for real ordering. Say the direction rule when migrating.
- Relates to for "see also". It is GA, so no labels or body links in its place.
- A relation that crosses an audience boundary is recorded on the more private side only, or not at all.
- Relations described only in prose are candidates for a person, not links.

## Views

- One view per question a reader asks: board by Status, roadmap by Target date, hierarchy, per-repo tables, a triage or needs-review table.
- Name views after the question, not after a client or person. View names are project-level data.
- Say the layout, filter, group, sort and visible fields for each. Say which settings plynth can create and which a person sets in the UI.

## Privacy

- No client names, hostnames, IPs, GUIDs, internal ids or people's names anywhere in the spec, Project titles, descriptions, view names, field names or field options. Use roles and generic names.
- Status updates and the Project README are project-level data too. Say who writes them and what they must not mention.

## Shape

- Roughly two screens. Tables for Projects, fields and views. One line per rule.
- Every field says its scope. Every Project says its owner. Every open decision is listed as open, with the recommended answer marked as a recommendation.
