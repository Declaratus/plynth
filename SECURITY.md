# Security Policy

## Token handling

plynth accepts any GitHub API bearer token via `PLYNTH_TOKEN` (or
`--token`). Three token types are supported, in order of preference
for new setups: fine-grained PAT (recommended), classic PAT, and
GitHub App tokens (installation or user access). Each is detailed
below.

### Fine-grained PAT — recommended

Fine-grained PATs scope access to specific repositories and one
organization, and are the preferred token type for new setups. The
permission set below is documented end-to-end for github.com targets.
GHES 3.19 supports fine-grained PATs but has a documentation gap on
the org-level *Projects* permission — see the GHES caveat below
before assuming this works the same way against a GHES instance.

Create the token at:

- **github.com:** <https://github.com/settings/personal-access-tokens/new>
- **GHES:** `https://<your-ghes-host>/settings/personal-access-tokens/new`

Configure with:

- **Resource owner:** the GitHub organization that will own the project.
- **Repository access:** *Only select repositories* → select the repo
  named in the instance config's `repo.name`.
- **Repository permissions:**
  - **Issues:** *Read and write* — covers `createIssue`, `updateIssue`
    (body rewrites in Phase 5), `addBlockedBy` (dependency edges), and
    the REST `POST /repos/{owner}/{repo}/milestones` endpoint, which
    lives under the Issues permission scope.
  - **Metadata:** *Read-only* — required for any repository access and
    auto-granted alongside the other permissions.
- **Organization permissions:**
  - **Projects:** *Read and write* — covers `createProjectV2`,
    `createProjectV2Field`, the project-fields query, `addProjectV2ItemById`,
    and `updateProjectV2ItemFieldValue`. Projects are owned at the
    organization level, so this permission lives in the *Organization*
    section, not under the repository.

No other permissions are required for the standard bootstrap flow.
Granting `Contents`, `Pull requests`, or org-wide repo access broadens
the blast radius of a leaked token without enabling any plynth feature.

If your instance config sets `repo.create: true`, plynth additionally
needs to call `POST /orgs/{org}/repos` before Phase 1. Add organization
*Administration: Read and write* to the fine-grained PAT for that case.
A classic PAT with `repo` scope already covers it. Drop the permission
once the repo exists; subsequent runs against the same repo do not need it.

> **GHES 3.19 caveat.** GHES 3.19 exposes the ProjectV2 GraphQL
> mutations, but the required fine-grained PAT permission for
> ProjectV2 mutations is not documented in the GHES 3.19 fine-grained
> PAT permissions reference. On github.com, the equivalent permission
> is documented as an organization-level *Projects* permission, but
> that section is absent from the GHES 3.19 page. For GHES 3.19,
> verify fine-grained PAT behavior against the target instance; if it
> fails or the permission is unavailable in the UI, use a classic PAT
> with `project` scope (next section) or a GitHub App installation
> token.

#### Confirmed against GHES 3.19 (2026-05)

A fine-grained PAT with repository *Issues: Read and write* and
organization *Projects: Read and write* drove a full plynth bootstrap
end-to-end: project, fields, milestones, issues, project items,
dependencies, and state file. The permission set documented in
[PR #39](https://github.com/Declaratus/plynth/pull/39) is the path that
worked.

### Classic PAT — supported alternative

Classic PATs with `repo` + `project` scopes authenticate plynth against
either target type. They grant much broader access than plynth's
operations call for, so prefer a fine-grained PAT in new setups against
github.com. Pick a classic PAT when:

- Your GHES instance has fine-grained PATs disabled by admin policy.
- You want a permission story that is documented end-to-end on GHES
  3.19 today (see the caveat above on ProjectV2).
- You're on an older GHES release where fine-grained PATs are not yet GA.

### GitHub Apps

GitHub App authentication is supported on both github.com and GHES
3.19+, in two flavours that plynth treats identically:

- **Installation tokens (IAT)** — minted server-side from the App's
  private key. Suitable for automation. This is also the documented
  fallback when a fine-grained PAT can't grant the *Projects*
  permission on a GHES 3.19 instance (see the caveat above).
- **User access tokens (UAT)** — minted via the OAuth user-consent
  flow.

The plynth CLI does not currently bootstrap either flow itself, so
this is a "bring your own token" path rather than an integrated one.
If you have an external flow that produces a token of either type,
plynth will accept it via `PLYNTH_TOKEN`. The App's installation
permissions must match the fine-grained PAT permission set above
(repository *Issues* + *Metadata*, organization *Projects*).

### Operational handling

**Do:**
- Pass the token via the `PLYNTH_TOKEN` environment variable.
- Use `--token` for one-off invocations where environment variables are inconvenient.
- Store tokens in a secrets management system, not in files on disk.
- Rotate tokens regularly and revoke unused ones.

**Do not:**
- Commit tokens to any repository — including instance config YAML files.
- Log tokens or include them in bug reports.
- Set tokens in shell history. To avoid this, use:
  ```bash
  read -rs PLYNTH_TOKEN && export PLYNTH_TOKEN
  ```

> **Note:** `GHES_TOKEN` is accepted for one release as a deprecated fallback
> and will be removed in v0.4.0.

Instance config files (`*.yaml`) intentionally have no `token` field.
The token is always supplied at runtime, never stored in YAML.

## Reporting a vulnerability

If you discover a security vulnerability in plynth, please report it privately
rather than opening a public GitHub issue.

**Contact:** open a [GitHub Security Advisory](https://github.com/Declaratus/plynth/security/advisories/new)
or email the maintainer directly (address on the GitHub profile).

Please include:
- A description of the vulnerability and its impact.
- Steps to reproduce or a minimal proof-of-concept.
- Any suggested mitigation.

We aim to acknowledge reports within 48 hours and to publish a fix within 14 days
for confirmed critical issues.

### Response SLA by severity

| Severity | Acknowledge | Fix |
| --- | --- | --- |
| Critical | 48 hours | 14 days |
| High | 72 hours | 30 days |
| Medium | 1 week | 90 days |
| Low | Best-effort | Best-effort |

### End-user mitigation

While waiting for a fix to ship:

- Pin to the most recent unaffected release until a fix ships.
- Watch the [Releases page](https://github.com/Declaratus/plynth/releases) — security fixes are tagged in the release notes.

## Supported versions

Only the latest release receives security fixes.
Pin to a specific release tag in production and update promptly when a security
fix is published.
