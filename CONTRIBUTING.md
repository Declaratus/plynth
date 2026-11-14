# Contributing to plynth

## Development setup

```bash
git clone https://github.com/Declaratus/plynth.git
cd plynth
pip install -e ".[dev]"
```

The `[dev]` extra includes pytest, ruff, mypy, and the test helpers.

## Running tests

```bash
pytest -q
```

Tests live in `tests/`. The suite uses `responses` to mock all HTTP calls —
no live GitHub or GHES instance required.

## Lint and type-check

Check (what CI runs — must pass before opening a PR):

```bash
ruff check .
ruff format --check .
mypy plynth
```

Apply formatting locally (modifies files in place):

```bash
ruff format .
```

Configuration lives in `pyproject.toml` under `[tool.ruff]` and `[tool.mypy]`.

## Security checks

CI runs two additional security gates on every PR and on push to `main`:

- **CodeQL** ([.github/workflows/codeql.yml](.github/workflows/codeql.yml))
  runs static analysis with the `security-and-quality` query suite.
  Findings appear under the repository's **Security** tab. Also runs
  weekly on Mondays so advisories added to the CodeQL database in
  quiet weeks are still caught.
- **pip-audit** (the `audit` job in [.github/workflows/ci.yml](.github/workflows/ci.yml))
  scans plynth's declared runtime dependencies — the
  `[project] dependencies` block in `pyproject.toml`, not the `[dev]`
  extras (pytest, ruff, mypy, responses, etc.) which never ship to
  users — for known CVEs. Fails the build on any reported vulnerability,
  including ones without an upstream fix yet. If the team accepts the
  risk of a specific advisory, add it under the action's `ignore-vulns`
  input in `ci.yml` with an inline comment documenting the rationale
  and the date to revisit.

## Commit messages

Pull request titles follow [Conventional Commits](https://www.conventionalcommits.org/),
and the `pr-title` check enforces it:

```
<type>(<optional scope>): <short description>
```

Types: `feat`, `fix`, `perf`, `revert`, `docs`, `ci`, `chore`, `test`,
`build`, `style`, `refactor`. Put `!` after the type for a breaking change,
such as `feat!: drop the GHES_TOKEN fallback`.

Pull requests are squash-merged, so the title becomes the commit message and
the changelog entry: write it for someone using plynth. `feat`, `fix`,
`perf`, `revert` and `deps` changes are listed in the changelog and start a
release. `docs`, `ci`, `chore`, `test`, `build`, `style` and `refactor`
changes are left out of the changelog and never start a release on their
own, unless marked as breaking. A pull request with several user-facing changes can list
them in its description, one Conventional Commit per change with a blank
line between, inside a `BEGIN_COMMIT_OVERRIDE` / `END_COMMIT_OVERRIDE` block.

Keep the subject line under 72 characters.
Reference issues where applicable: `fixes #42`.

## Pull request flow

1. Fork or branch from `main`.
2. Make changes. Add or update tests for any behaviour change.
3. Run `ruff check .`, `ruff format --check .`, `mypy plynth`, and `pytest -q` locally.
4. Open a PR against `main` with a Conventional Commit title. Fill in the PR template.
5. CI must pass before merge.

`CHANGELOG.md` is written by release-please from pull request titles; don't
edit it by hand.

## Releases

release-please keeps a release pull request open, `chore(main): release X.Y.Z`,
with the next version and its changelog entry. Merging it bumps
`pyproject.toml` and `plynth/__init__.py`, tags `vX.Y.Z` and creates a draft
GitHub Release. The tag starts the release workflow, which publishes to PyPI
and then publishes the GitHub Release with the wheel and sdist attached.
Release candidates are tags pushed by hand, such as `v0.5.0-rc.1`; the
release workflow builds them with the tag's version (`0.5.0rc1`), so nobody
bumps version files by hand. See
[docs/pypi-publishing-setup.md](docs/pypi-publishing-setup.md).

## Authentication in tests

Tests must never use real tokens or make real API calls.
All HTTP interactions are mocked via the `responses` library.
Never commit `PLYNTH_TOKEN` (or the deprecated `GHES_TOKEN`) or any credential
to the repository — see [SECURITY.md](SECURITY.md).

## Scope

plynth is intentionally minimal in its runtime dependencies (pydantic, pyyaml, requests).
Before adding a dependency, consider whether the functionality can be
implemented without it. Open an issue to discuss if unsure.

## Good places to start

If you are looking for a first contribution, see the
[good-first-issue queue](https://github.com/Declaratus/plynth/issues?q=is%3Aissue+is%3Aopen+label%3A%22good-first-issue%22).
The active milestone view at <https://github.com/Declaratus/plynth/milestones>
shows what's currently in flight and what's queued for the next release.
