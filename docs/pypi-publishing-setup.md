# PyPI Trusted Publishing setup (one-time, manual)

The release workflow at `.github/workflows/release.yml` publishes to PyPI
on every `v*` tag using **OIDC trusted publishing** — no API token, no
repo secrets to leak. The OIDC binding requires two manual setup steps
that cannot be automated from this PR. Do them **before** merging this
PR (or at least before pushing the first `v*` tag); the first publish
will 403 otherwise.

## 1. Add the pending publisher on PyPI

Log in to <https://pypi.org> with the account that will own the project
and go to **Account → Publishing → Add a pending publisher**:

| Field             | Value             |
| ----------------- | ----------------- |
| PyPI project name | `plynth`          |
| Owner             | `Declaratus`      |
| Repository name   | `plynth`          |
| Workflow filename | `release.yml`     |
| Environment name  | `pypi`            |

> Verify the project name `plynth` is still available before doing this:
> `pip index versions plynth` or
> <https://pypi.org/project/plynth/>. If it's taken, fall back to
> `plynth-cli` or `declaratus-plynth` and update the workflow's `url`
> + `pyproject.toml`'s `name` to match.

## 2. Create the GitHub environment

In `Declaratus/plynth` → **Settings → Environments → New environment**.

- Name (must match the workflow exactly): **`pypi`**
- Optional: under **Deployment branches**, restrict to tag pattern
  `v*` so only release tags can deploy.

No secrets are required. OIDC handles authentication.

## 3. Bump the version

Update `pyproject.toml` and `plynth/__init__.py` from `0.3.0.dev0` to
the release version (e.g. `0.3.0`). Commit on `main`. Hatchling reads
`pyproject.toml`'s `[project] version`, so the artifact filenames
match the tag.

## 4. Dry-run the release pipeline

Before tagging the real release, push an `-rc` tag to verify the binding:

```bash
git tag v0.3.0-rc1
git push origin v0.3.0-rc1
```

Watch the **release** workflow run. All three jobs (`build`,
`pypi-publish`, `github-release`) must turn green. If `pypi-publish`
fails with a 403 mentioning OIDC, the pending-publisher entry from
step 1 is missing or has a typo.

After a successful dry run, yank the rc on PyPI and continue with the
real tag:

```bash
git tag v0.3.0
git push origin v0.3.0
```

## 5. Verify

```bash
pipx install plynth==0.3.0
plynth --help
```

The GitHub Release page for `v0.3.0` should have the wheel and sdist
attached.
