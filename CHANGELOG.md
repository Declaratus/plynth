# Changelog

All notable changes to plynth are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.2.0] — 2026-05-02

Maturity foundation release. No runtime behavior changes for the happy path;
adds OSS scaffolding, lint/type-check gates, a 77-test suite, friendly errors
with request timeouts, and CI.

### Added

#### OSS scaffolding (PR 1)
- LICENSE (Apache 2.0).
- CHANGELOG.md, CONTRIBUTING.md, SECURITY.md.
- GitHub issue and PR templates under `.github/`.

#### Lint, format, and type-check (PR 2)
- `[tool.ruff]` — lint + format configuration (line-length 100, target py39,
  rules E/F/W/I/UP/B/SIM, with per-file ignores for the GraphQL query strings).
- `[tool.mypy]` — strict mode, with narrow per-module overrides on
  `engine.graphql_client`, `engine.rest_client`, and `engine.phases`.
- `[tool.pytest.ini_options]` — `testpaths`, `--strict-markers`.
- `plynth/py.typed` — PEP 561 marker so downstream consumers see plynth's
  types.

#### Tests (PRs 3 and 4)
- `tests/` foundation with shared fixtures (`minimal-template.yaml`,
  `minimal-instance.yaml`).
- Unit tests for `models.template`, `models.instance`, `models.state`,
  `engine.planner`, `utils.references`, and CLI argparse layout.
- HTTP-mocked integration tests for `engine.api_base` (write-delay, retry),
  `engine.graphql_client` (every mutation/query plus error paths),
  `engine.rest_client` (milestone create + error mapping), and an end-to-end
  orchestrator test running Phases 1, 2, 3, 4, 5, 7 against an in-test GraphQL
  dispatcher; verifies state both in-memory and reloaded from disk, and
  exercises the persisted resume path with a fresh orchestrator.

#### Errors and timeouts (PR 5)
- `plynth/errors.py` — `PlynthError` (base) → `AuthError`, `NotFoundError`,
  `NetworkError`, `ConfigError`. `GraphQLError` is now a `PlynthError`.
- `--timeout-seconds` CLI flag (default 30, must be > 0; validated by
  argparse) on both `create` and `resolve`.
- `request_timeout_s` parameter on `GHESClient`, threaded through every
  `session.post` in `engine.graphql_client` and `engine.rest_client`.
- Friendly error mapping:
  - HTTP 401 → `AuthError` ("Token rejected by `{ghes_url}`; verify GHES_TOKEN scopes include `repo` and `project`.")
  - REST 404 → `NotFoundError` ("Repository `{owner}/{repo}` not found on `{ghes_url}`")
  - GraphQL "Could not resolve to ..." / "could not be found" → `NotFoundError`
  - `requests.Timeout` / `ConnectionError` → `NetworkError` (with the configured timeout in the message)
- `cli.main` wraps dispatch in `try/except PlynthError` → prints
  `Error: {e}` to stderr and exits with code 2. Unexpected exceptions still
  raise so tracebacks aren't hidden in `--verbose`.
- YAML / Pydantic validation failures during template/instance/state loading
  now raise `ConfigError` with a friendly message.

#### CI and release tooling (PR 6)
- `.github/workflows/ci.yml` — matrix on Python 3.9 / 3.11 / 3.12. Steps:
  ruff check, ruff format --check, mypy plynth, pytest -q.
- `.github/dependabot.yml` — weekly updates for pip and github-actions.

### Changed
- Codebase reformatted with `ruff format`.
- `cli.py` — argparse setup extracted into `build_parser()` so tests can
  exercise the real parser.
- `models.instance` — `start_date` validator chains the underlying
  `ValueError` with `raise ... from e` (B904).

### Removed
- Dead no-op loop in `engine.planner` dry-run formatter.

---

## [0.1.0] — 2026-05-01

Initial release. Core engine complete and functional against GHES 3.19.

### Added
- **Template schema** (`plynth/models/template.py`) — Pydantic v2 models for
  `TemplateDefinition`, `FieldDefinition`, `MilestoneDefinition`, `IssueDefinition`,
  placeholder specs, status options, views, and pruning rules.
- **Instance config schema** (`plynth/models/instance.py`) — `InstanceConfig`,
  `RepoConfig`, `ProjectConfig` with validators (URL trailing-slash trim, date format).
- **Execution plan model** (`plynth/models/plan.py`) — `ExecutionPlan`,
  `ResolvedIssue`, `ResolvedMilestone`, `ResolvedField`.
- **State file model** (`plynth/models/state.py`) — `StateFile` with per-phase
  checkpoint tracking, SHA-256 template/instance hashes, and resume support.
- **Planner** (`plynth/engine/planner.py`) — pure computation: placeholder
  resolution, milestone/issue filtering (skip_milestones, skip_issues, pruning),
  dependency graph trimming, dry-run formatter.
- **GraphQL client** (`plynth/engine/graphql_client.py`) — all Phase 1–5 mutations
  and preflight queries; write delay enforcement; retry on 429/503.
- **REST client** (`plynth/engine/rest_client.py`) — milestone creation via
  `POST /repos/{owner}/{repo}/milestones` (only REST operation; createMilestone
  not available in GHES 3.19 GraphQL).
- **Base HTTP client** (`plynth/engine/api_base.py`) — `GHESClient` with Bearer
  auth, configurable write delay, and exponential-backoff retry.
- **Phase orchestrator** (`plynth/engine/phases.py`) — Phases 1–7 with state
  checkpointing and resume logic.
- **Cross-reference resolver** (`plynth/utils/references.py`) — `{PREFIX}-###`
  → `#real_number` substitution with longest-first matching and skipped-ref
  strikethrough.
- **CLI** (`plynth/cli.py`) — `plynth create` and `plynth resolve` subcommands;
  `--dry-run`, `--token`, `--state-dir`, `--write-delay-ms`, `--verbose`.
- **GraphQL query/mutation strings** (`plynth/queries/`) — all mutations and
  queries as module-level constants.
- **agent-reference docs** (`docs/`) — design spec, orchestrator spec,
  planner spec, API client spec, example template (17 issues, 5 milestones),
  and example instance config.

[Unreleased]: https://github.com/Declaratus/plynth/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Declaratus/plynth/releases/tag/v0.2.0
[0.1.0]: https://github.com/Declaratus/plynth/releases/tag/v0.1.0
