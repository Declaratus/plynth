# Example spec

A filled-in spec for a fictional program. Names are generic: `example-org` is a Team-plan org, `example-user` is a personal account, and the partner pilot is work that must stay out of the org.

```markdown
# Board spec: Payments platform

As of 14 Nov 2026. Plan: Team (example-org). Build only what is listed here.

**Goal:** One place to plan the payments platform across its three repos.
**Audiences:** org engineers see the platform board; the partner pilot is visible only to example-user and the pilot repo's collaborators, never to example-org.

## Projects

| Project | Owner (type) | Why this owner | Visibility | Holds | Never holds |
|---|---|---|---|---|---|
| Payments platform | example-org (org) | every org engineer reads it | private | issues from example-org/api, example-org/web, example-org/infra and parents in example-org/portfolio | any item from example-user/partner-pilot |
| Partner pilot | example-user (user) | its field values and status updates name the pilot, and org owners and apps can read every org Project | private | issues from example-user/partner-pilot | items from example-org repos |

- New Projects. The two untitled example-org Projects are closed after the move.

## Items

| Source | Destination repo | Arrives in Project by |
|---|---|---|
| API and service work | example-org/api | auto-add `is:issue` |
| Front-end work | example-org/web | auto-add `is:issue` |
| Infra work | example-org/infra | auto-add `is:issue` |
| Initiatives and cross-repo epics | example-org/portfolio | auto-add `is:issue` |
| Pilot work | example-user/partner-pilot | auto-add `is:issue` (Partner pilot) |

- Auto-add workflows used: 4 of 5 on Payments platform; 1 of 1 on Partner pilot (the user account is on Free).
- Existing items: imported once with a query import per repo, since auto-add does not back-fill.

## Fields

| Field | Type | Scope | Why |
|---|---|---|---|
| Priority | single select | issue field (example-org) | default, shared |
| Target date | date | issue field (example-org) | default, read by the roadmap and by eyrl |
| Effort | number | issue field (example-org) | default, shared |
| Area | multi-select: API, Web, Infra | issue field (example-org) | an epic can span areas |
| Status | single select: Todo, In progress, Done | project field (Payments platform) | board columns |
| Status | single select: Todo, In progress, Done | project field (Partner pilot) | same options on purpose, so rollups match |
| Pilot stage | single select: Scoping, Trial, Review | project field (Partner pilot) | only means something on the pilot board |

- Issue fields used: 4 of 25 at example-org. Partner pilot uses Priority and Target date as issue fields at example-user (2 of 25).
- Fields that differ by owner: none. Both Status fields share options.

## Issue types

- Initiative, Epic, Task, Bug at example-org. Initiative and Epic do not exist yet; fallback labels `type:initiative`, `type:epic`.
- Partner pilot uses labels only (personal account).

## Hierarchy

- Shape: Initiative → Epic → Task. Deepest path 3 of 8. Widest parent 40 of 100.
- Cross-repo parents live in example-org/portfolio.
- Inheritance: children created under a portfolio epic inherit Payments platform, which is right. Pilot work is never parented under an org item; the pilot has its own top-level epic in example-user/partner-pilot.

## Relations

- Blocked by: kept as GitHub dependencies, target blocked by source.
- Relates to: native relates-to links.
- Across the org and pilot boundary: recorded on the pilot side only, as a relates-to from the pilot issue.

## Views

| Project | View | Layout | Filter / group / sort | Set by |
|---|---|---|---|---|
| Payments platform | Board | board | group Status | plynth |
| Payments platform | Roadmap | roadmap | Target date, group Area | plynth (name, layout, filter), UI (dates, group) |
| Payments platform | Hierarchy | table, hierarchy on | `is:open` | plynth (view), UI (hierarchy) |
| Payments platform | API, Web, Infra | table | `repo:example-org/<repo>` | plynth |
| Partner pilot | Board | board | group Pilot stage | UI |

## Visibility

- Payments platform project-level data is safe for every example-org member and installed app. Status updates never mention the pilot.
- Partner pilot field values and status updates may name the pilot; that Project is never shared with example-org.

## Build steps

| Step | Tool | Web UI only |
|---|---|---|
| Create Payments platform, Status field, views | plynth | no |
| Turn on hierarchy in the Hierarchy view | person | yes |
| Add Area as an issue field | person (org settings) | yes |
| Auto-add workflows for four repos | person | yes |
| Import existing issues | GitHub Projects MCP or gh api | no |
| Later field and item changes | mendrik apply | no |
| Drift check | mendrik inspect, then board-reviewer | no |
| Portfolio rollup across both boards | eyrl, only for readers of both | no |

## Open decisions

1. Issue types: add Initiative and Epic at example-org, or keep labels. Recommended: add them, because the hierarchy view groups by type.
```

Why it works:

- Two Projects, one per audience boundary. Everything else is a view.
- Shared fields are org issue fields; only board columns and a pilot-only lane are project fields.
- Inheritance is stated per boundary, and private work is never parented under an org item.
- The auto-add count is checked against each plan's cap, and back-fill has its own step.
- Web-UI-only steps are listed for a person instead of being left implicit.
