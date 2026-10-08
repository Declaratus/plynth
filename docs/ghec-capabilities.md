# GitHub.com/GHEC capability review

Reviewed 2026-10-08. This is a current adoption reference. Older design and
orchestrator specifications describe the GHES 3.19 implementation baseline;
they are not a claim that cloud capabilities remain frozen at that release.

| Capability | Cloud evidence | plynth behavior / next step |
|---|---|---|
| Projects REST API | [September 2025 release](https://github.blog/changelog/2025-09-11-a-rest-api-for-github-projects-sub-issues-improvements-and-more/) | Keep working GraphQL paths; adopt REST where it adds an implemented capability. |
| Project view creation | [Current REST view API](https://docs.github.com/en/rest/projects/views) | Opt-in basic organization views implemented below; no assumption of GHES support. |
| Cross-organization sub-issues | [September 2025 release](https://github.blog/changelog/2025-09-11-a-rest-api-for-github-projects-sub-issues-improvements-and-more/) | Not implemented by plynth; [qualified identity / hierarchy work](https://github.com/Declaratus/plynth/issues/71). |
| Hierarchy in table views | [January 2026 preview](https://github.blog/changelog/2026-01-15-hierarchy-view-now-available-in-github-projects/) | Enable Show hierarchy in the UI; a dependency edge does not create a sub-issue. |
| Query-based import and reparenting | [February 2026 update](https://github.blog/changelog/2026-02-19-github-projects-import-items-based-on-a-query-and-hierarchy-view-improvements/) | Useful for adding existing work to a portfolio. Query import is a starting population, not a continuous synchronization contract. |
| Organization issue fields | [July 2026 GA](https://github.blog/changelog/2026-07-02-issue-fields-are-now-generally-available/) | Separate from Project fields. Preserve scope and IDs when adding support; GHES delivery is announced for 3.23. |
| Multi-select fields | [August 2026 GA](https://github.blog/changelog/2026-08-07-connecting-issues-and-multi-select-field-support/) | Not supported by the template field model or executor; do not declare a multi-select value as single-select. |
| Private repository issue views and relates-to | [September 2026 GA](https://github.blog/changelog/2026-09-25-personal-saved-views-for-repository-issues-and-more/) | Personal repository filters differ from shared Project views. Relates-to needs a distinct relationship type. |
| Agent workflows and issue intents | [Workflow preview](https://github.blog/changelog/2026-02-13-github-agentic-workflows-are-now-in-technical-preview/), [issue controls preview](https://github.blog/changelog/2026-07-23-agent-automation-controls-in-github-issues-in-public-preview/) | Separate optional triage experiment; deterministic bootstrap does not emit agent suggestions or rationales. |

## Opt-in Project views

```yaml
views:
  - name: Intake
    layout: table
    create: true
    filter_query: 'is:issue is:open'
  - name: Delivery
    layout: board
    create: true
    filter_query: 'is:issue is:open'
```

Supported targets are `github.com` and `https://api.github.com`.
GHEC data-residency hosts (`*.ghe.com`) are not routed by this implementation.
`create` defaults to false, including in existing templates. View names
and filter queries resolve instance placeholders; opted-in names must be
unique after resolution. Dry-run shows every view's action and counts
creation calls. `description` is documentation and is not sent to the API.

This first path creates only name, layout and filter. The API also supports
numeric field IDs for grouping, visible fields and sorting, but mapping
them from template/GraphQL field identities is follow-up work. An opted-in
view with legacy `group_by`, `slice_by`, `sort`, `filter` or `visible_fields`
fails validation rather than dropping that configuration. Set those in
the UI after creation. The legacy structured filter is not `filter_query`.
Show hierarchy is also manual; creating a table view does not enable it.

Phase 6 calls `POST /orgs/{org}/projectsV2/{project_number}/views` with
API version `2026-03-10`. Other REST operations retain their existing
version. The token needs organization Projects write permission. Each
confirmed view response is checkpointed by resolved name with node ID,
number and URL; a partial resume skips those views. This is bootstrap,
not view reconciliation. HTTP 5xx, timeout or connection failures are not
automatically replayed: inspect the remote Project before resuming because
an unconfirmed POST may have succeeded. A changed name creates a new view;
it does not rename one. Keep the state file and normal hash guards.

## Portfolio/intake bootstrap

The [template](examples/ghec-portfolio-template.yaml) and
[instance](examples/declaratus-portfolio-instance.yaml) create one
organization Project, single-select fields and four basic views. They
create no issues, milestones or native hierarchy: add existing issues by
URL after bootstrap. Review before applying:

```bash
plynth create --template docs/examples/ghec-portfolio-template.yaml \
  --instance docs/examples/declaratus-portfolio-instance.yaml --dry-run --format json
```

The instance points at `Declaratus/eyrl`, an existing repository;
`repo.create` is false. Applying uses the normal `PLYNTH_TOKEN` workflow.
Do not apply again with a fresh state file to the same pilot. Confirm the
new Project is private before adding private work. Plynth currently does
not attach an existing Project, link repository tabs, or apply the
configured project description; set those in the GitHub UI.

## Identity and access constraints

Project ownership does not require all issues to live in the same repo or
organization. Cross-org references link existing repository issues; they
do not transfer issue ownership. Project visibility also does not grant
repository access: [backing issue access still applies](https://docs.github.com/en/issues/planning-and-tracking-with-projects/managing-your-project/managing-visibility-of-your-projects).
Manager access needs a Project role and the appropriate repository role.
Personal saved views are filters over permitted content, not a privacy
policy for aggregation.

Use host plus repository-qualified identity for live issues. Template IDs,
GraphQL node IDs, REST database IDs, issue numbers and Project item IDs are
different identifiers. Milestones stay repository-scoped; explicitly verify
inheritance and Project membership across repository boundaries.

A [fine-grained PAT has one resource owner](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).
Multi-org reads need a credential strategy, not merely a broader search.
Also verify cross-org relationship writes on the chosen target: the release
announces cross-org support, while current REST add-sub-issue parameter
documentation still contains a same-owner restriction. Record actual API/UI
results rather than assuming all surfaces are identical.
