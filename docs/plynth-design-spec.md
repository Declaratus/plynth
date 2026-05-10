# GitHub Projects as Code (plynth) -- Design Specification

## Purpose

Automate the full lifecycle of GitHub Project instantiation from declarative YAML templates. Eliminate the manual 30-60 minute Phase 2 process (copy template, convert drafts, assign milestones, replace placeholders, wire dependencies) and remove the assumption that target repositories have sequential issue numbers.

The tool reads a **template definition** (YAML) and an **instance config** (YAML), then orchestrates the GraphQL mutations against GHES to produce a fully populated project with real issues, milestones assigned, placeholders resolved, and cross-references wired.

---

## Architecture

```
┌─────────────────────────┐     ┌──────────────────────────┐
│  Template Definition    │     │  Instance Config          │
│  (YAML, version-       │     │  (YAML, per-vendor or    │
│   controlled in repo)   │     │   per-app)               │
│                         │     │                          │
│  - fields               │     │  - vendor: Example Vendor     │
│  - milestones           │     │  - prefix: EX           │
│  - issues               │     │  - platform: kubernetes         │
│  - views                │     │  - repo: example-repo       │
│  - pruning rules        │     │  - org: example-org             │
│  - placeholders schema  │     │  - skip_milestones: [M2] │
└────────────┬────────────┘     │  - skip_issues: []       │
             │                  │  - field_overrides: {}    │
             │                  └─────────────┬────────────┘
             │                                │
             ▼                                ▼
       ┌─────────────────────────────────────────┐
       │            plynth engine                  │
       │                                         │
       │  Phase 1: Create project + fields       │
       │  Phase 2: Create repo milestones        │
       │  Phase 3: Create issues (capture IDs)   │
       │  Phase 4: Assign milestones + fields    │
       │  Phase 5: Resolve cross-references      │
       │  Phase 6: Configure views               │
       │  Phase 7: Emit mapping file             │
       │                                         │
       └────────────┬────────────────────────────┘
                    │
                    ▼
       ┌─────────────────────────────────────────┐
       │  GHES GraphQL API (primary)             │
       │    Projects, fields, issues,            │
       │    dependencies, item field values      │
       │  GHES REST API (milestones only)        │
       └─────────────────────────────────────────┘
                    │
                    ▼
       ┌─────────────────────────────────────────┐
       │  Output: mapping.yaml                   │
       │                                         │
       │  project_id: PVT_xxx                    │
       │  project_url: https://ghes/orgs/...     │
       │  issues:                                │
       │    EX-001: { number: 47, node_id: ... }│
       │    EX-002: { number: 48, node_id: ... }│
       │  milestones:                            │
       │    M1: { number: 3, node_id: ... }      │
       └─────────────────────────────────────────┘
```

---

## Schema versioning

Templates and state files carry a `schema_version` string so older artifacts keep parsing across plynth releases. Templates that omit the key are parsed as `1.0` (pre-M1); state files default the same way.

| version | adds |
|---------|------|
| `1.0` | base schema (pre-M1): placeholders, fields, milestones, issues, views, pruning, optional `status:` block |
| `1.1` | M1: template-level `defaults:`, rich `FieldOption` (color/description/default/aliases/deprecated), `reconciliation:` stub |
| `1.2` | M2: `labels:` catalogue, issue `labels` / `issue_type` (planned) |
| `1.3` | M3: `label_rules:` (planned) |
| `1.4` | M4: instance `label_overrides` / `issue_overrides` (planned) |
| `1.5` | M5: verifier subcommand and `VerifyReport` (planned) |

The engine accepts an M1 template either with or without `schema_version: "1.1"` today; the table is the contract for what each version adds, not a runtime gate. Templates that intend to use a future-version feature should declare the matching version so the contract is auditable in the file.

State-file migrations live in `StateFile._apply_compat_shims` (`plynth/models/state.py`). It owns every dict-shape transformation needed to upgrade an older state file into the current in-memory shape (e.g. the pre-v0.3 `ghes_url` → `target` rename). Pydantic field defaults zero-fill missing keys, so genuinely additive M1+ fields need no shim, just a default on the model.

---

## Template Definition Schema

This is the machine-readable source of truth. One file per template, version-controlled in the repository.
See `docs/example-template.yaml` for a complete working example. The annotated excerpt below documents every schema key.

```yaml
# example-template.yaml  (excerpt -- see full file for complete issue set)
---
schema_version: "1.0"

template:
  name: "Application Service Onboarding"
  description: >-
    Golden-path template for onboarding a new managed service.
    Covers repository setup, deployment, observability, security, and automation.
  version: "v1"

# ─── Placeholders ───────────────────────────────────────────────
# Keys are substitution tokens used throughout the template.
# instance.values must supply a value for every required: true key.
# Optional keys default to empty string if not supplied.
placeholders:
  APP:
    description: "Application or service name"
    example: "Acme Scheduler"
    required: true
  PREFIX:
    description: "2-4 character issue prefix (appears in titles and {PREFIX}-### cross-refs)"
    example: "ACME"
    required: true
  TEAM:
    description: "Owning team name"
    example: "Platform Engineering"
    required: true

# ─── Status Field ───────────────────────────────────────────────
# Overrides the built-in Status field options and order.
# Color must be one of: GRAY BLUE YELLOW RED PURPLE GREEN
status:
  - value: "Backlog"
    color: "GRAY"
  - value: "In Progress"
    color: "YELLOW"
  - value: "Blocked"
    color: "RED"
  - value: "Done"
    color: "GREEN"

# ─── Custom Fields ──────────────────────────────────────────────
# type: single_select is the only supported field type in v1.
# Placeholders in option values (e.g., "{TEAM}") are resolved at instantiation.
fields:
  - id: workstream
    name: "Workstream"
    type: single_select
    options:
      - "Documentation"
      - "Infrastructure"
      - "Operations"
      - "Security"
      - "Integration"

  - id: priority
    name: "Priority"
    type: single_select
    # Options can be plain strings (legacy) or rich objects with color,
    # description, default, aliases, and deprecated. See docs/options.md
    # for the full schema. Mixed forms are allowed in the same field.
    options:
      - value: "P1 -- Critical Path"
        color: RED
        description: "Blocks downstream milestones if it slips."
      - value: "P2 -- Important"
        color: YELLOW
        default: true
      - "P3 -- When Capacity Allows"

  - id: owner
    name: "Owner"
    type: single_select
    options:
      - "{TEAM}"         # Resolved to "Platform Engineering" (or whatever TEAM is)
      - "Platform"
      - "External"

# ─── Defaults ───────────────────────────────────────────────────
# Template-level defaults applied to every issue unless overridden.
# Precedence (lowest to highest): engine fallback, template defaults,
# per-issue values, instance.field_overrides. Last writer wins per key.
# Labels are intentionally deferred until the labels-and-issue-types
# feature lands.
defaults:
  fields:
    workstream: "Operations"

# ─── Reconciliation (reserved namespace) ─────────────────────────
# Reserved for the verify subcommand and the companion reconcile
# skill. Today only `mode: none` is honored. `report_only` parses
# but is treated identically to `none` until reconciliation ships.
# Reserving the namespace now avoids a schema break later because
# every model uses extra="forbid".
reconciliation:
  mode: none
  verify_after_apply: false

# ─── Milestones ─────────────────────────────────────────────────
# Created as GitHub repository milestones (REST, not GraphQL).
# due_date = instance.start_date + due_offset_weeks.
# optional: true milestones may be excluded via instance.skip_milestones.
milestones:
  - id: M1
    title: "M1: Repository and Documentation Foundation"
    description: >-
      Repository, docs site, and catalog registration.
      No external dependencies. Scaffolding for everything that follows.
    due_offset_weeks: 3
    optional: false

  - id: M2
    title: "M2: Deployment and Configuration"
    description: >-
      Initial deployment or refresh of {APP}. Optional: skip if service is
      already running in production with no infrastructure change planned.
    due_offset_weeks: 6
    optional: true          # Can be excluded via instance.skip_milestones: [M2]

  - id: M3
    title: "M3: Observability and Operations"
    description: "Monitoring, alerting, runbook, and on-call coverage."
    due_offset_weeks: 9
    optional: false

# ─── Issues ─────────────────────────────────────────────────────
# template_id: unique zero-padded 3-digit string within this template.
#   Used in blocked_by/blocks and as {PREFIX}-### cross-reference tokens.
#
# blocked_by / blocks: list of template_ids.
#   blocked_by: ["003"] = this issue cannot start until 003 completes.
#   blocks: ["007"]     = this issue must complete before 007 can start.
#   Both directions resolve to addBlockedBy(issueId, blockingIssueId) in Phase 5.
#
# {PREFIX}-### in body text: left unresolved until Phase 5, when the engine
#   replaces them with #real_issue_number using the Phase 3 mapping.
#   Skipped issue refs are replaced with ~~{PREFIX}-003~~ (skipped -- M2 excluded).
issues:
  - template_id: "001"
    title: "{PREFIX}-001: Create {APP} repository"
    milestone_id: M1
    fields:
      workstream: "Documentation"
      priority: "P1 -- Critical Path"
      owner: "{TEAM}"
    blocked_by: []
    blocks: ["002", "003", "006"]
    body: |
      Create the canonical repository for {APP} with branch protections and CODEOWNERS.

      **Dependencies:**
      - Blocked by: None
      - Blocks: {PREFIX}-002, {PREFIX}-003, {PREFIX}-006

      Acceptance criteria:
      - Repository created and accessible
      - Branch protection enabled (PR review + status checks)
      - CODEOWNERS reflects team ownership

  - template_id: "002"
    title: "{PREFIX}-002: Configure branch protection and CODEOWNERS"
    milestone_id: M1
    fields:
      workstream: "Documentation"
      priority: "P1 -- Critical Path"
      owner: "{TEAM}"
    blocked_by: ["001"]
    blocks: []
    body: |
      Verify branch protection and review routing.

      **Dependencies:**
      - Blocked by: {PREFIX}-001 (repository must exist)
      - Blocks: None

  - template_id: "006"
    title: "{PREFIX}-006: Deploy {APP} to target environment"
    milestone_id: M2
    fields:
      workstream: "Infrastructure"
      priority: "P1 -- Critical Path"
      owner: "{TEAM}"
    blocked_by: ["001"]
    blocks: ["008"]
    body: |
      Deploy {APP}. Document every step -- this record becomes the rebuild runbook.

      **Dependencies:**
      - Blocked by: {PREFIX}-001 (repository needed)
      - Blocks: {PREFIX}-008 (monitoring needs a running service)

  # ... remaining issues follow the same structure
  # See docs/example-template.yaml for the complete 17-issue set.

# ─── Views ──────────────────────────────────────────────────────
# Declarative documentation only -- not automated by the engine.
# GHES 3.19 does not expose createProjectV2View mutations.
# Configure views manually after project creation (5-10 minutes).
views:
  - name: "Board"
    layout: board
    group_by: status
    visible_fields: ["workstream", "priority", "owner"]

  - name: "Roadmap"
    layout: roadmap
    group_by: milestone
    slice_by: owner
    visible_fields: ["priority"]

# ─── Pruning Rules (schema feature example -- not active above) ──────────────
# Allows conditional issue inclusion based on a field value set after a
# decision point. The planner applies pruning before any API calls.
#
# pruning:
#   trigger_issue: "004"             # Decision is made when this issue closes
#   decision_field: deployment_type  # Instance sets this field to pick a rule
#   rules:
#     - field_value: "new-deployment"
#       keep_issues: ["005", "006", "007"]
#       remove_issues: []
#     - field_value: "existing-service"
#       keep_issues: []
#       remove_issues: ["005", "006", "007"]
```

---

## Instance Config Schema

Small file, one per instantiation. Supplies the concrete values for a specific project.

See `docs/example-instance.yaml` for the complete annotated file. Key fields:

```yaml
# example-instance.yaml  (key fields -- see full file for complete annotations)
---
template: example-template.yaml

# GitHub API base URL.
# GHES:        "https://ghes.example.com"
# GitHub.com:  "https://api.github.com"  (near-term roadmap: different URL conventions)
ghes_url: "https://ghes.example.com"

org: "myorg"

# Must supply all required: true placeholders from the template.
values:
  APP: "Acme Scheduler"
  PREFIX: "ACME"
  TEAM: "Platform Engineering"

repo:
  name: "acme-scheduler"
  create: false    # false = existing repo; engine handles non-sequential issue numbers

project:
  name: "Acme Scheduler -- Service Onboarding"
  description: >-
    Service onboarding tracking for Acme Scheduler. Instantiated {DATE}.

# Skip M2 -- service is already deployed, no infrastructure change needed.
# All M2 issues (005, 006, 007) are excluded automatically.
# Cross-references to M2 issues in other bodies → strikethrough in Phase 5.
skip_milestones:
  - M2

skip_issues: []      # Exclude individual issues by template_id

field_overrides: {}  # Override field values per issue: {"017": {priority: "P2 -- Important"}}

start_date: "2026-05-01"   # Milestone due dates = start_date + due_offset_weeks

# pruning_decision:          # Only when template defines pruning rules
#   deployment_type: "existing-service"
```

---

## Execution Algorithm

Seven phases, executed in strict order. Each phase is idempotent where possible (re-running after a partial failure skips already-created resources by checking for existence first).

### Phase 1: Create Project and Fields

```
1. Validate instance config against template (all required placeholders supplied,
   referenced milestones/issues exist in template)
2. Build effective issue list:
   a. Start with all issues in template
   b. Remove issues whose milestone_id is in skip_milestones
   c. Remove issues whose template_id is in skip_issues
   d. If pruning_decision is set, apply pruning rules
   e. Validate remaining dependency graph (warn if a blocked_by target was removed)
3. Resolve owner node ID:
   a. Query organization by login  →  owner_id
   b. Query repository by name  →  repository_id (needed for createIssue)
4. createProjectV2(ownerId, title)  →  project_id
5. For each custom field in template.fields:
   a. Resolve placeholders in option values (e.g., "Vendor ({VENDOR})" → "Vendor (Example Vendor)")
   b. createProjectV2Field(projectId, name, dataType, singleSelectOptions)  →  field_id
6. Re-query field IDs and option IDs:
   a. Query: node(id: project_id) { ... on ProjectV2 { fields { ... } } }
   b. For each field, capture field_id and for single-select fields, each option's id
   c. Store as field_id_by_slug and option_id_by_slug in mapping
   This step is required because createProjectV2Field returns the field but
   the option IDs must be queried separately for updateProjectV2ItemFieldValue.
7. Update Status field options if template specifies custom status values
```

### Phase 2: Create Repository Milestones

REST is required here -- `createMilestone` does not exist in the GHES 3.19 GraphQL
mutation reference. This is the only phase that uses REST.

```
1. For each milestone in template.milestones:
   a. Skip if milestone.id is in skip_milestones
   b. Resolve placeholders in title and description
   c. Calculate due_date from start_date + due_offset_weeks
   d. POST /repos/{org}/{repo}/milestones  →  milestone_number, node_id
   e. Store milestone_id → { number: milestone_number, node_id: node_id }
```

### Phase 3: Create Issues (Capture Real Numbers)

This is the critical phase that solves the existing-repo problem. Uses GraphQL
`createIssue` which supports `milestoneId` at creation time on GHES 3.19.

```
1. For each issue in effective issue list (ordered by template_id):
   a. Resolve all placeholders in title and body:
      - {APP} → instance.values.APP  (or whichever placeholders the template defines)
      - {PREFIX} → instance.values.PREFIX
      - {TEAM} → instance.values.TEAM
   b. Leave {PREFIX}-### references in body UNRESOLVED (Phase 5 handles these)
   c. createIssue(repositoryId, title, body, milestoneId)  →  issue.id, issue.number
      Note: CreateIssueInput also exposes projectIds, but the Project V2 docs
      require addProjectV2ItemById followed by updateProjectV2ItemFieldValue,
      so do NOT use projectIds here. Project association happens in Phase 4.
   d. Store mapping: template_id → { number: issue.number, node_id: issue.id }
2. Log the complete mapping table
```

The engine does NOT assume issue numbers are sequential. It captures whatever GitHub assigns and uses the mapping for all subsequent operations.

### Phase 4: Add Issues to Project and Set Field Values

The Project V2 docs require a two-step sequence: add the item first, then set
field values. These cannot be combined into a single mutation. Also note that
`updateProjectV2ItemFieldValue` cannot set Assignees, Labels, Milestone, or
Repository -- those are issue-level properties handled via `createIssue` or
`updateIssue`. Milestone is already assigned at issue creation time (Phase 3).

```
1. For each created issue:
   a. addProjectV2ItemById(projectId, contentId=issue.node_id)  →  item_id
      Note: if the item already exists (re-run), the existing item_id is returned.
   b. For each field assignment in issue.fields:
      - Look up field_id and option_id from Phase 1 re-query mapping
      - updateProjectV2ItemFieldValue(projectId, itemId, fieldId,
          value: { singleSelectOptionId: option_id })
   c. Set Status to "Backlog" (default) via same mutation
```

### Phase 5: Resolve Cross-References and Wire Dependencies

Two-pass approach: body text rewrite + dependency linking via `addBlockedBy`.

```
1. Build the full reference map:
   {PREFIX}-001 → #47
   {PREFIX}-002 → #48
   {PREFIX}-003 → #49
   ... (from Phase 3 mapping)

2. For each created issue:
   a. Fetch current body text (already known from Phase 3, or re-query if needed)
   b. Find all {PREFIX}-### patterns in body
   c. Replace each with #real_number using the reference map
   d. If a referenced issue was skipped (not in map):
      - Replace with strikethrough: "~~{PREFIX}-006~~ (skipped -- M2 excluded)"
      - Append note to Dependencies section
   e. updateIssue(id, body: resolved_body) via GraphQL

3. Wire dependency relationships via addBlockedBy:
   a. For each issue, iterate blocked_by list:
      - addBlockedBy(issueId=this.node_id, blockingIssueId=target.node_id)
   b. For each issue, iterate blocks list:
      - addBlockedBy(issueId=target.node_id, blockingIssueId=this.node_id)
      (blocks is the inverse -- "this blocks Y" means "Y is blocked by this")
   c. Skip links where the target was in a skipped milestone/issue
   d. Log each dependency created
```

Note: `addBlockedBy` requires repository-issue node IDs, not draft item IDs.
Since our engine creates real issues in Phase 3, this is always satisfied.
Draft issues cannot participate in dependency relationships.

### Phase 6: Views (Template-Seeded, Not Automated)

GHES 3.19 does not expose `createProjectV2View`, `updateProjectV2View`, or
`deleteProjectV2View` mutations. View configuration is explicitly out of scope
for engine automation in v1.

The practical fallback is strong: GHES 3.19 project templates and project copies
carry forward views, custom fields, draft issues, field values, workflows, and
insights. The recommended approach:

```
Option A (preferred): Maintain a golden template project in GitHub with views
  pre-configured. Use plynth to handle fields, issues, milestones, dependencies,
  and field assignments. Views are inherited from the template copy.

Option B: Create the project via plynth, then manually configure views (4 views,
  ~5 minutes). The view definitions in the YAML serve as documentation for what
  to configure, even though the engine does not automate them.
```

The `views` section in the template YAML is retained as declarative documentation
of the intended view configuration, not as an executable spec.

### Phase 7: Emit Mapping File

The mapping file is the persistent state artifact. It enables re-resolve mode,
drift detection, and audit trail. Every ID captured during execution is recorded.

```
1. Write mapping.yaml to working directory:

   schema_version: "1.0"
   created_at: "2026-03-16T14:30:00Z"
   template:
     file: "example-template.yaml"
     version: "v3"
   instance:
     file: "example-instance.yaml"
     config_hash: "sha256:abc123..."
   ghes_url: "https://ghes.example.com"
   org: "example-org"
   repo:
     name: "example-repo"
     node_id: "R_xxx"
   project:
     node_id: "PVT_xxx"
     url: "https://ghes.example.com/orgs/example-org/projects/12"
     number: 12
   fields:
     workstream:
       node_id: "PVTSSF_xxx"
       options:
         "Documentation": "pvtssfo_xxx"
         "Infrastructure": "pvtssfo_yyy"
         # ... all options with node IDs
     # ... all fields
   milestones:
     M1:
       number: 3
       node_id: "MI_xxx"
     M3:
       number: 4
       node_id: "MI_yyy"
     # M2 skipped
   issues:
     "001":
       number: 47
       node_id: "I_xxx"
       item_id: "PVTI_xxx"
       title: "EX-001: Create vendor repo from docs template"
     "002":
       number: 48
       node_id: "I_yyy"
       item_id: "PVTI_yyy"
       title: "EX-002: Configure and publish GitHub Pages doc site"
     # ... all issues
   dependencies_created:
     - blocker: "001"
       blocked: "002"
     # ... all dependency edges
   skipped:
     milestones: ["M2"]
     issues: ["005", "006", "007", "008"]

2. Optionally commit mapping.yaml to the target repo (provides audit trail)
```

---

## The Existing Repo Problem -- Solved

The entire design hinges on **never assuming issue numbers**. Today's manual process works by:

1. Creating a fresh repo → issues start at #1
2. Creating issues in template order → {PREFIX}-001 = #1, {PREFIX}-002 = #2, etc.
3. Writing dependency references as `#1`, `#2` directly

This breaks on any repo with existing issues. The engine solves it by:

1. Creating issues in order → GitHub assigns whatever numbers come next (#41, #42, ...)
2. Capturing the actual number for each template_id
3. Resolving `{PREFIX}-###` → `#real_number` in a separate pass using the mapping

The mapping file also enables downstream tooling: a second script could re-run cross-reference resolution if issues are renumbered, or a reporting tool could map between template semantics and real issue URLs.

---

## Dependency Handling -- Design Decisions

### What GHES 3.19 supports (confirmed)

GHES 3.19 has two distinct relationship systems:

- **Dependencies:** `addBlockedBy` / `removeBlockedBy` -- "issue X is blocked by issue Y" semantics. Takes `issueId` and `blockingIssueId`. Returns `Issue` objects. Requires repository-backed issues (not drafts).
- **Sub-issues:** `addSubIssue` / `removeSubIssue` -- parent/child hierarchy. Separate from dependency tracking.

Note: the mutation name is `addBlockedBy`, not `addIssueDependency`. The latter does not exist in the GHES 3.19 GraphQL mutation reference.

### What the engine does

The `blocked_by` and `blocks` arrays in the template serve two purposes:

1. **Body text** -- human-readable dependency section in the issue description. Phase 5 resolves the `{PREFIX}-###` tokens to clickable `#number` links.

2. **Structured relationships** -- Phase 5 step 3 calls `addBlockedBy` to create formal dependency links that GitHub renders in the issue sidebar.

Normalization logic:
- `blocked_by: ["003", "005"]` on issue 006 → `addBlockedBy(issueId=006.node_id, blockingIssueId=003.node_id)` and `addBlockedBy(issueId=006.node_id, blockingIssueId=005.node_id)`
- `blocks: ["007", "009"]` on issue 006 → `addBlockedBy(issueId=007.node_id, blockingIssueId=006.node_id)` and `addBlockedBy(issueId=009.node_id, blockingIssueId=006.node_id)`

Both directions collapse to the same mutation with swapped arguments.

### Skipped dependency targets

When an issue references a dependency that was skipped (e.g., M2 issues referencing each other when M2 is excluded), the engine:

- Strikes through the reference in the body text
- Appends a note explaining why (milestone excluded)
- Skips the `addBlockedBy` call for that edge
- Logs a warning

This is better than silently dropping the reference -- it preserves the intent of the template while reflecting the actual instantiation decisions.

---

## Cloud Migration Template -- Pruning Extension

The cloud migration template has a pattern the managed service cluster template doesn't: service-model-conditional issues. The `pruning` block in the schema handles this declaratively:

```yaml
pruning:
  trigger_issue: "005"
  decision_field: service_model
  rules:
    - field_value: "IaaS"
      keep_issues: ["009", "010", ...]
      remove_issues: ["014", "015", "016"]
```

At instantiation time, if `pruning_decision.service_model` is set in the instance config, the engine applies the matching rule during Phase 1 step 2d (before any issues are created). If it's not set (decision hasn't been made yet), all issues are created and pruning happens later -- either manually or by re-running the engine with the decision set.

This means the same engine handles both templates without special-casing.

---

## Runtime Modes

### Mode 1: Full instantiation (default)

Creates everything from scratch. Used for new project onboarding.

```bash
plynth create --template example-template.yaml --instance example-instance.yaml
```

### Mode 2: Dry run

Validates config, resolves all placeholders, prints the execution plan without making any API calls. Useful for reviewing what will be created before committing.

```bash
plynth create --template example-template.yaml --instance example-instance.yaml --dry-run
```

### Mode 3: Re-resolve references

Re-runs Phase 5 only, using an existing mapping file. Useful if issues were manually added or reordered and cross-references need updating.

```bash
plynth resolve --mapping mapping.yaml
```

### Mode 4: Diff

Compares the current state of a project against its template definition. Shows drift: issues that were added, removed, or modified versus the template baseline.

```bash
plynth diff --template example-template.yaml --mapping mapping.yaml
```

---

## API Surface -- Confirmed for GHES 3.19

### GraphQL Mutations (primary client)

| Step | Mutation | Key Inputs | Returns |
|------|----------|-----------|---------|
| Create project | `createProjectV2` | `ownerId`, `title` | `projectV2.id` |
| Create field | `createProjectV2Field` | `projectId`, `name`, `dataType`, `singleSelectOptions` | `projectV2Field` |
| Create issue | `createIssue` | `repositoryId`, `title`, `body`, `milestoneId` | `issue.id`, `issue.number` |
| Add to project | `addProjectV2ItemById` | `projectId`, `contentId` | `item.id` |
| Set field value | `updateProjectV2ItemFieldValue` | `projectId`, `itemId`, `fieldId`, `value` | `projectV2Item` |
| Update issue body | `updateIssue` | `id`, `body` | `issue` |
| Add dependency | `addBlockedBy` | `issueId`, `blockingIssueId` | `issue`, `blockingIssue` |

### GraphQL Queries (preflight and re-query)

| Purpose | Query Pattern |
|---------|--------------|
| Org node ID | `organization(login:) { id }` |
| Repo node ID | `repository(owner:, name:) { id }` |
| Field + option IDs | `node(id: projectId) { ... on ProjectV2 { fields { ... } } }` |

### REST Endpoints (milestone creation only)

| Step | Endpoint | Why REST |
|------|----------|---------|
| Create milestone | `POST /repos/{owner}/{repo}/milestones` | `createMilestone` not in GHES 3.19 GraphQL |

### Not Available on GHES 3.19

| Capability | Status |
|-----------|--------|
| `createProjectV2View` | Not in mutation reference -- views are template-seeded only |
| `updateProjectV2View` | Not in mutation reference |
| `deleteProjectV2View` | Not in mutation reference |

### Constraints

- `updateProjectV2ItemFieldValue` **cannot** set Assignees, Labels, Milestone, or Repository. Those are issue-level properties set via `createIssue` or `updateIssue`.
- `addProjectV2ItemById` returns the existing item ID if the item is already on the project (safe for re-runs).
- `addBlockedBy` requires repository-issue node IDs, not draft item IDs. Draft issues cannot participate in dependency relationships.
- Items cannot be added and updated in the same mutation call. Add first, then set field values.

Authentication: Personal Access Token (PAT) with `repo` and `project` scopes, or a GitHub App installation token.

### Rate Limiting

GHES 3.19 GraphQL rate limits are disabled by default (confirm with site admin).
REST best practices: serialize mutating writes, pause at least 1 second between
POST/PATCH/PUT/DELETE calls, honor `Retry-After` and `x-ratelimit-reset` headers.

Engine config:
```yaml
api:
  write_delay_ms: 1000      # Delay between mutating calls
  max_retries: 3             # Retry count on transient failure
  backoff_multiplier: 2.0    # Exponential backoff factor
```

---

## Implementation Plan

### Phase A: Schema + CLI scaffold (design, this document) -- COMPLETE

Deliverable: This spec, reviewed and agreed. YAML schema finalized. API surface
confirmed against GHES 3.19 GraphQL mutation reference.

### Phase B: Core engine (Python + PyYAML + Pydantic + requests)

Technology stack: Python 3.9+, PyYAML, Pydantic (typed config models + JSON
Schema generation), requests (REST client for milestones), lightweight GraphQL
client (raw requests against `/api/graphql` endpoint).

Execution order, mapped to engine phases:

1. Pydantic models for template, instance config, and mapping file
2. Template + instance config parsing, validation, placeholder resolution
3. Effective issue list computation (skip milestones, skip issues, pruning rules)
4. GraphQL client: createProjectV2, createProjectV2Field, re-query field/option IDs
5. REST client: create milestones
6. GraphQL client: createIssue (with milestoneId), capture mapping
7. GraphQL client: addProjectV2ItemById + updateProjectV2ItemFieldValue
8. Cross-reference resolution: build map, rewrite bodies via updateIssue
9. Dependency wiring: addBlockedBy per edge
10. Mapping file output

Dry-run mode: steps 1-3 only, print execution plan.

### Phase C: Hardening + re-resolve mode

1. Idempotency guards (check for existing project/issues before creating)
2. Re-resolve mode: re-run step 8-9 from existing mapping file
3. JSON Schema generation from Pydantic models (editor autocomplete)
4. Error recovery: checkpoint mapping file after each phase so partial failures
   can be resumed

### Phase D: GitHub Action wrapper

`workflow_dispatch` with inputs for template path and instance config values.
Runs the engine on a self-hosted runner with GHES network access. Enables
self-service project creation.

### Phase E: Drift detection (read-only)

Compare live project state against template + mapping. Report drift without
mutating. Additive-only reconciliation as a future extension if needed.

---

## Locked Constraints (confirmed against GHES 3.19)

These are no longer open questions. They are hard constraints for Phase B.

1. **Views: not automatable.** GHES 3.19 does not expose `createProjectV2View`,
   `updateProjectV2View`, or `deleteProjectV2View` mutations. Views are
   template-seeded or manually configured. The YAML `views` section is
   declarative documentation, not executable spec.

2. **Dependencies: `addBlockedBy` / `removeBlockedBy` in GraphQL.** The mutation
   takes `issueId` and `blockingIssueId`. Normalization: `blocked_by: X` maps
   to `addBlockedBy(issueId=self, blockingIssueId=X)`. `blocks: Y` maps to
   `addBlockedBy(issueId=Y, blockingIssueId=self)`. Dependencies require
   repository issues, not draft items.

3. **Issue creation: GraphQL `createIssue` with `milestoneId`.** Single client
   for all issue operations. Do not use `projectIds` on CreateIssueInput --
   Project V2 requires the add-then-update sequence.

4. **Milestone creation: REST only.** `createMilestone` is not in the GHES 3.19
   GraphQL mutation reference. One REST endpoint, everything else GraphQL.

5. **Rate limiting: serialize writes, 1-second delay.** GraphQL rate limits are
   disabled by default on GHES, but the engine honors `Retry-After` headers
   defensively. Delay is configurable via instance config.

6. **Bootstrap-only in v1.** No reconciliation, no destructive updates. Template
   application is a one-time bootstrap. Drift detection (Phase E) is read-only
   reporting. Full reconciliation is a future version.

7. **Language: Python + PyYAML + Pydantic + requests.** Not zero-dependency --
   PyYAML and Pydantic are not in Python stdlib. Pydantic provides typed config
   models and can generate JSON Schema for editor autocomplete.

8. **Sub-issues are separate from dependencies.** `addSubIssue` exists for
   hierarchy, `addBlockedBy` exists for dependency tracking. The template schema
   uses `blocked_by` / `blocks` for dependencies. Sub-issue hierarchy is out of
   scope for v1 templates unless explicitly needed.
