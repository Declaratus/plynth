# plynth

[![CI](https://github.com/Declaratus/plynth/actions/workflows/ci.yml/badge.svg)](https://github.com/Declaratus/plynth/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

**Declarative project plans, materialized as GitHub Projects (and other backends).**

## What this project is

A Python CLI tool that bootstraps fully populated GitHub Projects from declarative YAML templates.

**Primary target:** GitHub.com (Projects v2 + Issues).
**Supported target:** GitHub Enterprise Server (GHES) 3.19.

plynth replaces a manual 30-60 minute process of copying project templates, converting draft issues to real issues, assigning milestones, replacing placeholder tokens, and wiring cross-reference dependencies. It reads a **template definition** (YAML) and an **instance config** (YAML), then orchestrates GraphQL/REST mutations to produce a project with real issues, milestones assigned, placeholders resolved, field values set, and dependency relationships wired.

## Configuration: target

Set `target` in your instance YAML to point plynth at GitHub.com or a GHES
host:

```yaml
target: github.com                       # or omit for the same default
target: https://api.github.com           # equivalent
target: https://ghes.example.com         # GHES — REST under /api/v3
```

Authenticate with `PLYNTH_TOKEN=ghp_...` (or `--token`). `GHES_TOKEN` is
accepted for one release with a deprecation warning.

## Technology stack

- Python 3.9+ (must run on RHEL 8/9)
- PyYAML -- YAML parsing
- Pydantic v2 -- typed config models, validation, JSON Schema generation
- requests -- HTTP client (GraphQL + REST)
- No heavy GQL library -- raw queries via requests against `/api/graphql`

## Project structure

```
plynth/
  __init__.py
  cli.py              # CLI entry point (argparse or click)
  models/
    __init__.py
    template.py        # Pydantic models for template YAML
    instance.py        # Pydantic models for instance config YAML
    state.py           # Pydantic models for state/mapping file
  engine/
    __init__.py
    planner.py         # Validates config, builds effective issue list, resolves placeholders
    graphql_client.py  # GraphQL client (queries + mutations against GHES)
    rest_client.py     # REST client (milestone creation only)
    phases.py          # Phase 1-7 orchestration
  queries/
    __init__.py
    mutations.py       # GraphQL mutation strings
    queries.py         # GraphQL query strings
  utils/
    __init__.py
    references.py      # Cross-reference resolution ({PREFIX}-### → #number)
README.md
pyproject.toml
```

> Example templates, instance configs, and the full design spec are being prepared in a follow-up sanitization pass and are not yet included in the repository.

## Locked constraints (confirmed against GHES 3.19 GraphQL docs; github.com behaves the same except where noted)

These are hard design decisions, not open questions. Do not revisit them.

1. **GraphQL-first, REST for milestones only.** `createMilestone` is not in the GHES 3.19 GraphQL mutation reference. Everything else uses GraphQL. (github.com also requires REST for milestone creation today.)

2. **Issue creation via GraphQL `createIssue`.** Supports `milestoneId` at creation time. Do NOT use `projectIds` on `CreateIssueInput` -- Project V2 requires `addProjectV2ItemById` then `updateProjectV2ItemFieldValue` as separate calls.

3. **Dependencies via `addBlockedBy` / `removeBlockedBy`.** NOT `addIssueDependency` (doesn't exist). Normalization: `blocked_by: X` → `addBlockedBy(issueId=self, blockingIssueId=X)`. `blocks: Y` → `addBlockedBy(issueId=Y, blockingIssueId=self)`. Requires repository issues, not drafts.

4. **Views are NOT automatable.** No `createProjectV2View` or `updateProjectV2View` mutations on GHES 3.19. Views section in template YAML is declarative documentation only.

5. **Bootstrap-only in v1.** No reconciliation, no destructive updates. Re-runs should be safe (idempotent where possible) but the tool does not diff desired vs actual state.

6. **Serial writes, 1-second delay between mutations.** GHES GraphQL rate limits are disabled by default but the engine honors `Retry-After` defensively. Delay is configurable.

7. **Items cannot be added and updated in the same call.** Must `addProjectV2ItemById` first, then `updateProjectV2ItemFieldValue` separately.

8. **`updateProjectV2ItemFieldValue` cannot set Assignees, Labels, Milestone, or Repository.** Those are issue-level properties handled via `createIssue` or `updateIssue`.

## Execution phases (strict order)

```
Phase 1: Validate config → resolve owner/repo IDs → createProjectV2 → createProjectV2Field → re-query field/option IDs
Phase 2: POST /repos/{owner}/{repo}/milestones (REST) → store number + node_id
Phase 3: createIssue (GraphQL, with milestoneId) → capture issue number + node_id per template_id
Phase 4: addProjectV2ItemById → updateProjectV2ItemFieldValue (per field per issue)
Phase 5: Resolve {PREFIX}-### → #real_number in issue bodies via updateIssue → addBlockedBy per dependency edge
Phase 6: Skip (views not automatable)
Phase 7: Write state file
```

State file is checkpointed after each phase so partial failures can resume.

## Key GraphQL mutations

```graphql
# Phase 1
mutation CreateProject($ownerId: ID!, $title: String!) {
  createProjectV2(input: {ownerId: $ownerId, title: $title}) {
    projectV2 { id number url }
  }
}

mutation CreateField($projectId: ID!, $name: String!, $dataType: ProjectV2CustomFieldType!, $options: [ProjectV2SingleSelectFieldOptionInput!]) {
  createProjectV2Field(input: {projectId: $projectId, name: $name, dataType: $dataType, singleSelectOptions: $options}) {
    projectV2Field { ... on ProjectV2SingleSelectField { id name options { id name } } }
  }
}

# Phase 3
mutation CreateIssue($repositoryId: ID!, $title: String!, $body: String!, $milestoneId: ID) {
  createIssue(input: {repositoryId: $repositoryId, title: $title, body: $body, milestoneId: $milestoneId}) {
    issue { id number title }
  }
}

# Phase 4
mutation AddItemToProject($projectId: ID!, $contentId: ID!) {
  addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
    item { id }
  }
}

mutation SetFieldValue($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
  updateProjectV2ItemFieldValue(input: {projectId: $projectId, itemId: $itemId, fieldId: $fieldId, value: {singleSelectOptionId: $optionId}}) {
    projectV2Item { id }
  }
}

# Phase 5
mutation UpdateIssueBody($issueId: ID!, $body: String!) {
  updateIssue(input: {id: $issueId, body: $body}) {
    issue { id }
  }
}

mutation AddBlockedBy($issueId: ID!, $blockingIssueId: ID!) {
  addBlockedBy(input: {issueId: $issueId, blockingIssueId: $blockingIssueId}) {
    issue { id }
    blockingIssue { id }
  }
}
```

## Key GraphQL queries

```graphql
# Preflight: resolve org and repo IDs
query GetOrgId($login: String!) {
  organization(login: $login) { id }
}

query GetRepoId($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) { id }
}

# After field creation: re-query field and option IDs
query GetProjectFields($projectId: ID!) {
  node(id: $projectId) {
    ... on ProjectV2 {
      fields(first: 20) {
        nodes {
          ... on ProjectV2SingleSelectField {
            id name options { id name }
          }
          ... on ProjectV2Field {
            id name
          }
        }
      }
    }
  }
}
```

## Implementation order for Phase B

Build in this order. Each step should be testable independently.

1. **Pydantic models** (`models/template.py`, `models/instance.py`, `models/state.py`)
   - Template: placeholders, fields, milestones, issues (with blocked_by/blocks), views, pruning rules
   - Instance: values, repo config, skip_milestones, skip_issues, field_overrides, api settings
   - State: run metadata, project/field/milestone/issue ID mappings, phase checkpoints, errors
   - Include `template_sha256` guard on state file
   - Include `body_sha256` per issue in state for re-resolve detection

2. **Planner** (`engine/planner.py`)
   - Load and validate template + instance config
   - Resolve placeholders in titles, bodies, field options
   - Build effective issue list (apply skip_milestones, skip_issues, pruning rules)
   - Validate dependency graph (warn if blocked_by target was removed)
   - Dry-run mode: print execution plan and exit

3. **GraphQL client** (`engine/graphql_client.py`)
   - Single `requests.Session` with auth header
   - Generic `execute(query, variables)` method
   - Configurable write delay between mutations
   - `Retry-After` / rate-limit header handling
   - All mutation strings in `queries/mutations.py`

4. **REST client** (`engine/rest_client.py`)
   - Milestone creation only
   - Same session/auth pattern as GraphQL client
   - Same write delay and retry logic

5. **Phase orchestration** (`engine/phases.py`)
   - Phase 1: create project + fields + re-query IDs
   - Phase 2: create milestones (REST)
   - Phase 3: create issues (GraphQL)
   - Phase 4: add to project + set field values
   - Phase 5: resolve cross-refs + wire dependencies
   - Phase 7: emit state file
   - Checkpoint state file after each phase
   - Resume logic: check state file phases, skip completed phases

6. **CLI** (`cli.py`)
   - `plynth create --template <path> --instance <path> [--dry-run]`
   - `plynth resolve --state <path>` (re-run Phase 5 only)
   - Auth via `PLYNTH_TOKEN` env var or `--token` flag

## What NOT to build in Phase B

- View automation (not supported on GHES 3.19)
- Drift detection / reconciliation (Phase E)
- GitHub Action wrapper (Phase D)
- Destructive operations (delete issues, remove fields)
- GitHub App authentication (PAT is sufficient for v1)

## Roadmap

- v0.3.0 (in flight): github.com support via `target`, PyPI trusted publishing.
- Post-0.3: drift detection, GitHub Action wrapper, additional backends.
