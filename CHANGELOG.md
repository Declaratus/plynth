# Changelog

All notable changes to plynth are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- LICENSE (Apache 2.0)
- CHANGELOG.md
- CONTRIBUTING.md
- SECURITY.md
- GitHub issue and PR templates (`.github/`)

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
- **Sanitized agent-reference docs** (`docs/`) — design spec, orchestrator spec,
  planner spec, API client spec, example template (17 issues, 5 milestones),
  and example instance config.

[Unreleased]: https://github.com/Declaratus/plynth/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Declaratus/plynth/releases/tag/v0.1.0
