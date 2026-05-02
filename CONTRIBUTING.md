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

## Commit messages

Use the conventional commit format:

```
<type>: <short description>

[optional body]
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

Keep the subject line under 72 characters.
Reference issues where applicable: `fixes #42`.

## Pull request flow

1. Fork or branch from `main`.
2. Make changes. Add or update tests for any behaviour change.
3. Run `ruff check .`, `ruff format --check .`, `mypy plynth`, and `pytest -q` locally.
4. Update `CHANGELOG.md` under `## [Unreleased]`.
5. Open a PR against `main`. Fill in the PR template.
6. CI must pass before merge.

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
