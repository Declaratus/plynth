# Changelog

All notable changes to plynth are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.4.0] — 2026-05-10

Closes the bootstrap loop: repo creation, GHES version probe, configurable
Status field, JSON dry-run. Tightens 401 / 403 error wording around
SECURITY.md and locks in the schema_version cadence for future M-series
templates.

### Added

- **JSON dry-run output** (#12). `plynth create --dry-run --format json`
  emits the resolved `ExecutionPlan` plus an `api_call_estimate` block
  as a JSON document with a stable `schema_version`. Lets CI plan
  diffs, bot summaries, and other tooling consume the plan
  programmatically instead of regex-scraping the text formatter.
  Default remains `--format text`. Schema documented in
  [docs/dry-run-json.md](docs/dry-run-json.md); the
  `api_call_estimate` keys are pinned by a test so accidental renames
  force a `schema_version` bump.
- **Rich field option objects** (#42). Single-select field options can now
  declare `color`, `description`, `default`, `aliases`, and `deprecated` as
  an object instead of a plain string. Plain strings still work; the two
  forms can mix in the same field. See `docs/options.md`. A new
  `allow_unknown_values: false` field-level guard (default) rejects any
  issue, template default, or instance override that references a value
  not declared in the field's options. Enforced at plan time so drift
  fails the run cleanly instead of silently skipping in Phase 4. Set
  `allow_unknown_values: true` to opt out per field. `color` is validated
  against the GHES 3.19 ProjectV2 color set at template parse time;
  options that omit `color` render as GRAY.
- **Template-level defaults** (#43). New optional `defaults.fields` section
  on the template applies field values to every issue unless overridden.
  Precedence: per-issue value > template default > engine fallback.
  Instance `field_overrides` retain top precedence. Labels deferred until
  the labels-and-issue-types feature lands.
- **`reconciliation:` namespace reserved** (#44). New optional
  `reconciliation` block on the template carries `mode`
  (`none` | `report_only`) and `verify_after_apply`. Today only
  `mode: none` is honored; the namespace is reserved now because every
  model uses `extra="forbid"`, so adding fields later breaks anyone who
  already put a placeholder block in. `verify_after_apply` will be wired
  to the verify subcommand when it ships.
- **GHES version detection** (#15). On startup, plynth now probes
  `GET {target}/api/v3/meta` for GHES targets and caches the parsed
  `installed_version` as a `(major, minor)` tuple on the base client. Used
  by `GitHubClient.warn_if_below(min_version, feature, log)` to emit a
  friendly warning when a feature requires a higher minor version than
  the detected one. github.com targets skip the probe (no version field
  in `/meta` and no useful gating). Detection failures (404, network
  error, malformed response) log a warning and leave the version as
  `None`; nothing fails. Prepares the ground for view-API gating
  (GHES 3.20+) once view automation lands.
- **Configurable Status field options** (#14). The template-level `status:`
  block, previously parsed but inert, now drives the project's built-in
  Status field. plynth overwrites GitHub's defaults (Backlog/Ready/In
  progress/In review/Done) with the declared list during Phase 1, in the
  order given. `default: true` on one option picks what new items receive
  in Phase 4, replacing the hard-coded `Backlog` lookup. Omitting the block
  keeps GitHub's defaults exactly as before. Status options share the rich
  `FieldOption` shape introduced in #42 (color, description, default,
  aliases, deprecated); the older `StatusOption` model is removed.
  Requires GHES 3.19+ (the `singleSelectOptions` field on
  `UpdateProjectV2FieldInput` shipped in cloud on 2024-12-12); plynth
  introspects the schema at the start of Phase 1 and fails with a clear
  message on older instances. Templates without a `status:` block run on
  any GHES version plynth otherwise supports. Verified end-to-end against
  GHES 3.19.4 — the public GraphQL mutation accepts the system Status
  field and preserves input order (the in-UI Projects settings flow
  re-sequences, but the API path does not).
- **Repo creation when `repo.create: true`** (#13). With `repo.create: true`
  in the instance config, Phase 1 creates the target repository (private)
  via REST before resolving its node ID, instead of failing with
  `NotFoundError`. Existing repos are a no-op; `repo.create: false`
  (default) keeps the old friendly error. Repo creation needs more than
  the standard plynth permissions: classic `repo` already covers it; a
  fine-grained PAT also needs organization *Administration: Read and write*.
  See SECURITY.md.

### Changed

- **schema_version cadence and load-path compat shims** (#45). The
  template-level `schema_version` field now defaults to `"1.0"`, so
  pre-M1 templates without the key keep parsing. M1 templates should
  declare `schema_version: "1.1"` to flag use of `defaults:`, rich
  `FieldOption`, and the `reconciliation:` stub; the engine accepts the
  string verbatim. The version cadence (1.0 through 1.5, with M2-M5
  planned) is documented in `docs/plynth-design-spec.md#schema-versioning`.
  State-file shape migrations now live in
  `StateFile._apply_compat_shims`, a single funnel for renames and
  relocations; the pre-v0.3 `ghes_url` → `target` rename moves under
  the new docstring. Pydantic defaults zero-fill genuinely additive
  fields, so M1+ keys absent from a v0.3-era state file load cleanly.
  Regression fixture: `tests/fixtures/v0_3-state.yaml` round-trips
  through `model_validate` / `model_dump` under the current schema.
- **403 retry policy split** (#41). `_handle_retry` previously retried any
  403 the same way it retried 429/502/503. GitHub uses 403 for two unrelated
  cases: rate limits / abuse detection (retryable) and permission denials
  (not). Plynth now only retries 403s that carry a positive rate-limit
  signal: `Retry-After` header, `X-RateLimit-Remaining: 0`, or a
  secondary-rate-limit phrase in the response body. Permission-denied 403s
  raise `AuthError` immediately with a pointer at SECURITY.md, instead of
  surfacing "Max retries exceeded" after spinning the loop. Repro that
  motivated the fix: a fine-grained PAT without repository Issues access
  used to fail Phase 2 milestone creation as a transient-looking timeout;
  now it fails fast with permission advice.
- **401 error wording** (#40). Both the GraphQL and REST 401 handlers
  now point at SECURITY.md and name all three supported token shapes
  (classic PAT, fine-grained PAT, GitHub App). Pre-#40 they only
  mentioned classic-PAT scopes, which contradicted the documented
  fine-grained and GitHub App paths. Wording centralized in
  `plynth.errors.token_rejected_message()` so the runtime can't drift
  away from SECURITY.md again. The repo-create 401 (only fires under
  `repo.create: true`) keeps its operation-specific Administration
  guidance unchanged.
- **SECURITY.md** now documents the exact PAT permissions plynth needs.
  A fine-grained PAT with repository *Issues: Read and write* +
  organization *Projects: Read and write* is the recommended shape on
  github.com. The same shape is intended to apply to GHES 3.19+, but
  GHES 3.19's fine-grained-PAT permissions reference does not currently
  document the org-level Projects permission for the ProjectV2 GraphQL
  mutations — verify against your instance before relying on it, or
  fall back to a classic PAT with `repo` + `project` scopes or a
  GitHub App installation token. GitHub App authentication (both
  installation tokens and user access tokens) is documented as a
  bring-your-own-token path; the CLI does not bootstrap either flow
  itself.
- **SECURITY.md** now notes that the documented fine-grained PAT
  permission set was confirmed against GHES 3.19 in 2026-05.

---

## [0.3.0] — 2026-05-02

github.com support, PyPI trusted publishing, and roadmap visibility.

### Added

- **PyPI Trusted Publishing** (`.github/workflows/release.yml`) on `v*` tags.
  Builds sdist + wheel, publishes to PyPI via OIDC (no API token in repo
  secrets), and creates a matching GitHub Release with the artifacts
  attached. `pipx install plynth` is now the recommended install path.
- **`target` config field** (`plynth/models/instance.py`) replacing `ghes_url`.
  Accepts `""`, `"github.com"`, or `"https://api.github.com"` for GitHub.com,
  and `"https://<host>"` for GHES. `https://github.com` (the web host),
  `http://...`, and bare hostnames are rejected with a fix-it message.
- **`derive_api_roots(target)`** helper in `plynth/engine/api_base.py`.
  Centralizes the (graphql_endpoint, rest_base) derivation: `/api/graphql` +
  `/api/v3/...` for GHES, `api.github.com/graphql` + `api.github.com/...` for
  GitHub.com.
- **Default request headers**: `User-Agent: plynth/<version>` (read via
  `importlib.metadata`) and `X-GitHub-Api-Version: 2022-11-28`. github.com
  rejects requests without a User-Agent on some paths.
- **`PLYNTH_TOKEN` environment variable** is now the canonical token source.

### Changed

- **`GHESClient` renamed to `GitHubClient`.** A `GHESClient` alias remains and
  emits a `DeprecationWarning` on instantiation; it will be removed in v0.4.0.
- **Instance `target` field replaces `ghes_url`.** A v0.2.0 instance file
  using `ghes_url:` now fails validation with a migration hint pointing at
  `target` and the v0.3.0 CHANGELOG entry.
- **State files**: `ghes_url` key silently migrates to `target` so v0.2.0
  in-flight runs keep resuming. State files are machine-written and a hard
  rename would gratuitously break resume.
- **`GHES_TOKEN` is deprecated**; the CLI still falls back to it for one
  release with a `DeprecationWarning` plus a stderr note.
- **Error messages** that previously printed `(GHES: <url>)` now print
  `(target: <display_target>)`, where `display_target` is `"github.com"` for
  the empty/default target.

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

[Unreleased]: https://github.com/Declaratus/plynth/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/Declaratus/plynth/releases/tag/v0.4.0
[0.3.0]: https://github.com/Declaratus/plynth/releases/tag/v0.3.0
[0.2.0]: https://github.com/Declaratus/plynth/releases/tag/v0.2.0
[0.1.0]: https://github.com/Declaratus/plynth/releases/tag/v0.1.0
