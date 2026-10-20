# CLAUDE.md

- Do not include Claude-Session URLs or session links in commit messages or PR descriptions. This repo is (or will be) public.

## Checks

Run the same checks CI runs before pushing. Dev dependencies live in `.venv`
(the SessionStart hook creates it in cloud sessions; locally, use
`pip install -e ".[dev]"` in an environment of your choice):

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy plynth
.venv/bin/pytest -q
```

CI tests Python 3.9 through 3.12, and ruff and mypy target 3.9, so avoid
syntax and stdlib APIs newer than 3.9. When `uv` is available, run the suite on
the oldest supported version with:

```bash
uv run --isolated --python 3.9 --with-editable ".[dev]" pytest -q
```

The test suite mocks all HTTP with `responses`; no token or live instance is
needed. User-facing changes get an entry under `## [Unreleased]` in
`CHANGELOG.md`.

## Live runs

`plynth` writes to real GitHub organizations when run without `--dry-run`.
Only run it live against a sandbox organization, and never commit a
`PLYNTH_TOKEN` value or a literal `--token` argument.
