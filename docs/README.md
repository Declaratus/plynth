# docs/ — plynth Agent Reference

This directory contains implementation specifications and example files for the
plynth engine. All documents are written for agent (LLM) consumption: precise,
structured, and implementation-accurate. Human-facing documentation will follow
once the core implementation is stable.

---

## Document Index

| File | Purpose | Use when |
|------|---------|----------|
| [plynth-design-spec.md](plynth-design-spec.md) | Master architecture spec: template schema, instance config schema, 7-phase execution algorithm, API surface, locked constraints | Understanding the full system design before implementing any component |
| [orchestrator-spec.md](orchestrator-spec.md) | Implementation spec for `plynth/engine/phases.py` and `plynth/cli.py`: exact Python class/method signatures, per-phase pseudocode, state checkpointing, resume logic | Implementing, extending, or debugging the phase orchestrator |
| [planner-spec.md](planner-spec.md) | Implementation spec for `plynth/engine/planner.py`: placeholder resolution algorithm, pruning logic, dependency graph trimming, `ExecutionPlan` model | Implementing or debugging the planner (pure computation, no API calls) |
| [api-client-spec.md](api-client-spec.md) | Implementation spec for `plynth/engine/api_base.py`, `graphql_client.py`, `rest_client.py`, `queries/`: GraphQL mutation/query strings, retry logic, write delay, error handling | Implementing or debugging API clients |
| [example-template.yaml](example-template.yaml) | Complete reference template: "Application Service Onboarding" (17 issues, 5 milestones, 4 custom fields). Demonstrates all schema features | Writing tests, adding new template features, understanding template structure |
| [example-instance.yaml](example-instance.yaml) | Instance config for example-template.yaml with M2 skipped | Writing tests, understanding instance config structure |

---

## System Overview

plynth reads a **template** (YAML) and an **instance config** (YAML), then
materializes a GitHub Project by orchestrating 7 sequential phases:

```
Phase 1  Create project + custom fields (GraphQL)
Phase 2  Create repository milestones (REST -- createMilestone not in GraphQL)
Phase 3  Create issues with milestone assignments (GraphQL)
Phase 4  Add issues to project + set custom field values (GraphQL)
Phase 5  Resolve {PREFIX}-### cross-references in bodies + wire addBlockedBy (GraphQL)
Phase 6  Views -- not automated (no createProjectV2View mutation on GHES 3.19)
Phase 7  Finalize state file
```

The state file (`*.plynth-state.yaml`) is checkpointed after each phase so that
partial failures can be resumed without re-creating already-created resources.

---

## Key Architectural Facts (quick reference)

**URL conventions (current implementation):**
- GraphQL endpoint: `{ghes_url}/api/graphql`
- REST endpoint: `{ghes_url}/api/v3/repos/{owner}/{repo}/milestones`
- These are GHES conventions. GitHub.com uses `https://api.github.com/graphql`
  and `https://api.github.com/repos/...` — URL normalization is a near-term roadmap item.

**Authentication:** Bearer token via `Authorization` header. Env var: `GHES_TOKEN`.
Scopes required: `repo` + `project`.

**Mutations used (all GraphQL unless noted):**
- `createProjectV2` — Phase 1
- `createProjectV2Field` — Phase 1
- `createIssue` — Phase 3 (with `milestoneId`)
- `addProjectV2ItemById` — Phase 4
- `updateProjectV2ItemFieldValue` — Phase 4
- `updateIssue` — Phase 5 (body rewrite)
- `addBlockedBy` — Phase 5 (dependency wiring)
- REST `POST /milestones` — Phase 2

**Not available on GHES 3.19:** `createProjectV2View`, `updateProjectV2View`,
`deleteProjectV2View`. Views are configured manually.

**Cannot be combined:** `addProjectV2ItemById` and `updateProjectV2ItemFieldValue`
must be separate calls. Milestones/Labels/Assignees cannot be set via
`updateProjectV2ItemFieldValue` — they are issue-level properties.

**Cross-reference resolution:** `{PREFIX}-###` patterns in issue bodies are
intentionally left unresolved through Phase 3. Phase 5 builds a map from
template_id → real GitHub issue number and rewrites all bodies in one pass.

**Issue numbers are never assumed sequential.** The engine captures whatever
number GitHub assigns and uses a template_id → real_number mapping throughout.

---

## Source Code Structure

```
plynth/
  __init__.py            version string
  __main__.py            python -m plynth entry point
  cli.py                 argparse CLI: 'create' and 'resolve' subcommands
  engine/
    api_base.py          GHESClient: session, auth, write delay, retry
    graphql_client.py    GraphQLClient: execute(), per-phase mutation methods
    rest_client.py       RESTClient: create_milestone()
    planner.py           plan(): produces ExecutionPlan from template + instance
    phases.py            PhaseOrchestrator: executes phases 1-7 with checkpointing
  models/
    template.py          TemplateDefinition, FieldDefinition, MilestoneDefinition, IssueDefinition
    instance.py          InstanceConfig, RepoConfig, ProjectConfig
    plan.py              ExecutionPlan, ResolvedIssue, ResolvedMilestone, ResolvedField
    state.py             StateFile, PhaseStatus, IssueState, MilestoneState, FieldState
    __init__.py          public re-exports
  queries/
    queries.py           GET_ORG_ID, GET_REPO_ID, GET_PROJECT_FIELDS
    mutations.py         CREATE_PROJECT, CREATE_FIELD, CREATE_ISSUE, ADD_ITEM_TO_PROJECT,
                         SET_FIELD_VALUE, UPDATE_ISSUE_BODY, ADD_BLOCKED_BY
  utils/
    references.py        resolve_crossrefs(): {PREFIX}-### → #number substitution
```

---

## Files NOT in this directory (deferred sanitization)

The following files exist locally but are not tracked in git until they are
sanitized of organization-specific content:

- `governance-workflow-template.yaml` — 57-issue template tied to an org-specific governance process
- `governance-instance.yaml` — instance config with org-specific team and repo names
- `governance-dryrun.md` — dry-run output tied to the governance template

These files demonstrate the engine working at scale (57 issues, multi-team field
options) and will be committed once their content is made fully generic.
