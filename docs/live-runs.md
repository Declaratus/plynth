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

`template` and `instance` are paths in the repository at the ref the workflow
runs on. To resume a failed `create`, or to `resolve`, set `state_run_id` to
the run ID whose `plynth-state` artifact to start from. State artifacts are
kept for 30 days.

Runs are serialized (one live run at a time per repository).

## One-time setup

### 1. Environments

In **Settings → Environments**, create:

- `live-read`: no protection rules.
- `live-write`: add yourself under **Required reviewers**. Every `create` and
  `resolve` then waits for approval before it writes. Optionally limit its
  deployment branches to `main`, at the cost of not running write configs from
  feature branches.

### 2. Credentials

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
3. In this repository, set variables `LIVE_APP_ID` (the app ID) and
   `LIVE_APP_OWNER` (the organization login), and secret
   `LIVE_APP_PRIVATE_KEY` (a private key generated for the app).

**Fine-grained personal access token.** Set secret `LIVE_TOKEN` to a token
whose resource owner is the target organization, with the same permissions as
above.

Secrets can live at repository level, or on both environments for tighter
scoping.

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
