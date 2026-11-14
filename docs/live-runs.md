# Live runs through GitHub Actions

`.github/workflows/live-run.yml` runs plynth against a live organization from
a manual trigger. Use it when the machine you work from cannot call the GitHub
API directly. Claude Code cloud sessions are one example: they can start the
workflow and read its log through the GitHub connector, but cannot reach
GraphQL themselves.

| `command` | What it does | Environment | Credentials |
|---|---|---|---|
| `dry-run` | `plynth create --dry-run`; plans offline | `live-read` | none |
| `create` | Creates the project; uploads the state file as the `plynth-state` artifact | `live-write` | required |
| `resolve` | Re-resolves cross-references from the state of an earlier run | `live-write` | required |

`template` and `instance` must be files tracked in the repository at the ref
the workflow runs on. The run stops before plynth starts if either is not, so
neither can point into the downloaded state or outside the checkout.

plynth sends its token to the API host of the instance's `target`. For
`create` and `resolve`, the run reads the instance file with plynth's own
loader and stops before it mints a token unless `target` is GitHub.com
(`github.com` or `https://api.github.com`). With the GitHub App, the
instance's `org` must also equal `LIVE_APP_OWNER`.

To resume a failed `create`, or to `resolve`, set `state_run_id` to the run ID
whose `plynth-state` artifact to start from. Before downloading anything, the
workflow checks through the API that this run is a `workflow_dispatch` run of
`live-run.yml` in this repository on a commit on `main`, and that its review
history holds an approval for `live-write`. Because `live-write` only deploys
from the `main` branch, an approved run ran the workflow from the head of
`main` when it was dispatched. The artifact therefore comes from a `create` or
`resolve` run that a `live-write` reviewer approved. Being on `main` is not
enough on its own: the commits of a branch merged with a merge commit or by
rebase join `main`'s history without being reviewed one by one, and a run
dispatched on a tag named `main` also reports `main` as its branch. A run with
no recorded approval, such as one from before `live-write` required a
reviewer, cannot be resumed from. State artifacts are kept for 30 days.

Runs are serialized (one live run at a time per repository).

## One-time setup

### Prerequisites

Environments, environment secrets and variables, and deployment branch rules
are available in every public repository, and in private repositories on
GitHub Pro, GitHub Team and GitHub Enterprise. **Required reviewers** is
narrower: on GitHub Free, Pro and Team it is only available in public
repositories, so a private repository needs GitHub Enterprise for it.

Do not add any write credential until `live-write` shows both a required
reviewer and the `main`-only branch rule as saved. If **Required reviewers**
is unavailable for your repository, do not store write credentials at all.

### 1. Environments

In **Settings → Environments**, create:

- `live-read`: no protection rules and no secrets at all. `dry-run` plans
  offline and needs no credentials.
- `live-write`: select **Required reviewers** and add yourself, deselect
  **Allow administrators to bypass configured protection rules**, and click
  **Save protection rules**. Every `create` and `resolve` then waits for
  approval before it writes, and no administrator can skip it. In the
  **Deployment branches** dropdown, choose **Selected branches and tags**,
  click **Add deployment branch or tag rule**, set Ref type to **Branch**,
  enter `main` and click **Add rule**. Both the reviewer and the branch rule
  are required: with the branch rule, a modified workflow on another branch
  cannot run in `live-write`. The cost is that write configs cannot run from
  feature branches.

  The branch rule only protects if `main` itself is protected. Add a branch
  protection rule or ruleset on `main` that blocks force pushes and requires
  a pull request with at least one approving review, with these options
  selected:

  - **Dismiss stale pull request approvals when new commits are pushed**
  - **Require approval of the most recent reviewable push**
  - **Require review from Code Owners** (recommended: `.github/CODEOWNERS`
    covers `.github/workflows/`)

  Without the first two, an approval survives later pushes: a writer can get
  a harmless pull request approved, push a changed workflow or instance file
  to it, and merge it. If anyone other than you holds the admin role or a
  bypass permission, also select **Do not allow bypassing the above
  settings** in a branch protection rule, or leave the bypass list of a
  ruleset empty. Also keep **Allow GitHub Actions to create and approve pull
  requests** turned off (**Settings → Actions → General**, under **Workflow
  permissions**, and in the organization's settings), so a workflow pushed to
  a branch cannot approve a pull request with `GITHUB_TOKEN`. Then a changed
  workflow or instance file reaches `main` only through review.

  Also make sure no tag can be named `main`. A run dispatched on such a tag
  runs the workflow from whatever commit the tag points at, while its branch
  reads `main`. First check that no such tag exists (the command prints
  nothing), and delete it if one does:

  ```bash
  git ls-remote origin refs/tags/main
  git push origin --delete refs/tags/main   # only if the line above printed one
  ```

  Then, in **Settings → Rules → Rulesets**, click **New ruleset → New tag
  ruleset**, set Enforcement status to **Active**, leave the bypass list
  empty, and under Target tags click **Add a target**, include tags by
  pattern, and enter `main`. Under Tag protections select **Restrict
  creations** and **Restrict updates**, and click **Create**.

  Before you approve a run:

  - Check its name, which shows every input, and that it runs on
    `refs/heads/main`.
  - If `state_run_id` is set, open that run and confirm that it is a `create`
    or `resolve` run that you approved. Its state file decides which
    repository, project and issues this run writes to.
  - Open the instance file on `main` and confirm that `target` is
    `github.com` and `org` is the synthetic organization you intend. The run
    refuses any other host, and with the GitHub App any org other than
    `LIVE_APP_OWNER`. With a personal access token the run does not check
    the org; the token can only write to its resource owner.
  - The instance files committed under `docs/` and `tests/` are examples,
    not live configs. `docs/example-instance.yaml` and
    `tests/fixtures/minimal-instance.yaml` point at `ghes.example.com`, so the
    run refuses them. `docs/examples/declaratus-portfolio-instance.yaml`
    names a real organization: never approve a run that uses it.

### 2. Credentials

Store the write credentials (secrets `LIVE_APP_PRIVATE_KEY` and `LIVE_TOKEN`)
only as environment secrets of `live-write`. Never store them as repository
secrets, or as organization secrets shared with this repository: those reach
every workflow in the repository, including one changed on a branch, without
passing the `live-write` reviewer. Set the variables `LIVE_APP_CLIENT_ID` and
`LIVE_APP_OWNER` on `live-write` too, not as repository variables:
environment variables can only be changed by repository admins, and only
write runs use them.

Delete every copy of `LIVE_APP_PRIVATE_KEY` or `LIVE_TOKEN` left anywhere
else: repository secrets, organization secrets shared with this repository,
and secrets on `live-read` (an earlier version of this page suggested both
environments). To check:

```bash
gh secret list                  # repository secrets
gh secret list --env live-read  # secrets on live-read
gh secret list --org ORG        # organization secrets and their visibility
```

If any branch other than `main` could have run a modified workflow while a
copy was reachable, rotate the app key or token. As a canary, every `dry-run`
fails at its first step if it can see a write credential, without printing
the value.

Configure one of the following. If both are present, the GitHub App wins.

**GitHub App (recommended).** Tokens last one hour and only reach
organizations where the app is installed, so a run cannot touch any other
organization even with a wrong config.

1. Create a GitHub App owned by the target organization, with webhooks off.
   Repository permissions: **Issues** read and write, **Metadata** read.
   Organization permissions: **Projects** read and write. Milestones, labels
   and issue dependencies are covered by **Issues**.
2. Install it on the target organization only, and only on the repositories
   plynth writes issues to.
3. On the `live-write` environment, set variables `LIVE_APP_CLIENT_ID` (the
   app's client ID, not its numeric app ID) and `LIVE_APP_OWNER` (the
   organization login), and secret `LIVE_APP_PRIVATE_KEY` (a private key
   generated for the app).

**Fine-grained personal access token.** On the `live-write` environment, set
secret `LIVE_TOKEN` to a token whose resource owner is the target
organization, with the same permissions as above.

## Triggering

From the Actions tab (**Live run → Run workflow**), or with the GitHub CLI:

```bash
gh workflow run live-run.yml --ref main \
  -f command=create \
  -f template=path/to/template.yaml \
  -f instance=path/to/instance.yaml
```

## Public logs

Workflow logs and artifacts of a public repository are visible to anyone.
Only point live runs at an organization that holds synthetic data, and keep
real organization names out of committed instance configs.
