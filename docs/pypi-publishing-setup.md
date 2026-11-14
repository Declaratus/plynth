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

## 3. Versions and tags

Releases go through release-please (see `CONTRIBUTING.md`). Merging its
release pull request bumps `pyproject.toml` and `plynth/__init__.py`,
creates the `vX.Y.Z` tag and a draft GitHub Release. The tag starts
`release.yml`, which checks that the wheel's version matches the tag,
publishes to PyPI, then attaches the wheel and sdist to the draft and
publishes it. The GitHub Release is only published once PyPI has the files.

## 4. Release candidates

A release candidate is a tag pushed by hand. PyPI needs its own version
for it, so first merge a pull request that sets `pyproject.toml` and
`plynth/__init__.py` to the candidate version, such as `0.5.0rc1`, then
tag that commit:

```bash
git tag -a v0.5.0-rc.1 -m v0.5.0-rc.1 <commit>
git push origin v0.5.0-rc.1
```

`release.yml` compares versions the way pip does, so `v0.5.0-rc.1` matches
`0.5.0rc1`. The candidate is published to PyPI and as a GitHub prerelease
with generated notes. If `pypi-publish` fails with a 403 mentioning OIDC,
the pending-publisher entry from step 1 is missing or has a typo.

## 5. Verify

```bash
pipx install plynth==<version>
plynth --help
```

The GitHub Release page for the tag should have the wheel and sdist
attached.
