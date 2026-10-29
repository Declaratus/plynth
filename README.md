# plynth

plynth is a command-line tool for teams that set up the same GitHub Project many times. You describe the plan once as a YAML template, and plynth creates the Project, milestones, real issues, field values, and issue dependencies on GitHub.com or GitHub Enterprise Server.

[![CI](https://github.com/Declaratus/plynth/actions/workflows/ci.yml/badge.svg)](https://github.com/Declaratus/plynth/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

Without plynth, you copy a template Project by hand, convert draft items to issues, assign milestones, replace placeholder text, and link dependencies. plynth does those steps from two files:

- A **template**: the reusable plan, with placeholders such as `{APP}`.
- An **instance config**: the values for one project, plus the target org and repository.

## Install

```bash
pipx install plynth
```

<details>
<summary>Other install methods</summary>

Install with pip:

```bash
pip install plynth
```

Install from a clone of this repository:

```bash
pip install .
```

</details>

plynth needs Python 3.9 or later. CI tests Python 3.9 through 3.12.

## Quick start

1. Save a template as `template.yaml`:

   ```yaml
   template:
     name: "Service launch"
     description: "Two-issue starter plan."
     version: "1.0.0"

   placeholders:
     APP: {description: "Service name", example: "Acme", required: true}
     PREFIX: {description: "Cross-reference prefix", example: "ACME", required: true}

   fields:
     - id: priority
       name: "Priority"
       type: single_select
       options: ["P1", "P2"]

   milestones:
     - id: M1
       title: "{APP} foundation"
       description: "Get {APP} ready to run."
       due_offset_weeks: 2

   issues:
     - template_id: "001"
       title: "Create the {APP} repository"
       milestone_id: M1
       fields: {priority: "P1"}
       body: "Set up the repository for {APP}."
     - template_id: "002"
       title: "Write the {APP} runbook"
       milestone_id: M1
       fields: {priority: "P2"}
       blocked_by: ["001"]
       body: "Start after {PREFIX}-001 is done."
   ```

2. Save an instance config as `instance.yaml`:

   ```yaml
   template: template.yaml
   target: github.com
   org: example-org
   values:
     APP: "Acme"
     PREFIX: "ACME"
   repo:
     name: acme
   project:
     name: "Acme launch"
   start_date: "2026-11-02"
   ```

3. Preview the plan. A dry run needs no token and makes no API calls:

   ```bash
   plynth create --template template.yaml --instance instance.yaml --dry-run
   ```

   ```text
   === plynth Execution Plan ===
   Template: Service launch (1.0.0)
   Target:   github.com / example-org / acme
   Project:  Acme launch

   Milestones (1):
     M1: Acme foundation (due: 2026-11-16)

   Issues (2):
     001: Create the Acme repository [M1] [P1]
          blocked_by: (none) | blocks: (none)
     002: Write the Acme runbook [M1] [P2]
          blocked_by: 001 | blocks: (none)

   Fields (1):
     priority: Priority [single_select] (2 options)

   API call estimate:
     Milestones:     1 REST calls
     Issues:         2 GraphQL createIssue calls
     Add to project: 2 GraphQL addProjectV2ItemById calls
     Field values:   2 GraphQL updateProjectV2ItemFieldValue calls
     Body updates:   2 GraphQL updateIssue calls (cross-ref resolution)
     Dependencies:   1 GraphQL addBlockedBy calls
     Views:          0 REST create-view calls
     Total:          ~10 mutating calls (~10s at 1s delay)
   ```

For a template that uses every schema feature, see [docs/example-template.yaml](docs/example-template.yaml) and its [instance config](docs/example-instance.yaml).

## Usage

### Create the Project

The repository named in `repo.name` must already exist, unless you set `repo.create: true`. Set a token, then run `create` without `--dry-run`:

```bash
read -rs PLYNTH_TOKEN && export PLYNTH_TOKEN
plynth create --template template.yaml --instance instance.yaml
```

plynth writes a state file named after the project, such as `acme-launch.plynth-state.yaml`, in the current directory. Use `--state-dir` to write it somewhere else. The state file records the ID of everything plynth created.

### Resume after a failure

plynth saves the state file after each phase. If a run fails, fix the cause and run the same `create` command again. Completed phases are skipped. plynth refuses to resume if the template changed since the state file was created.

### Re-resolve cross-references

`resolve` re-runs only the step that replaces `{PREFIX}-###` references with real issue numbers and links dependencies:

```bash
plynth resolve --state acme-launch.plynth-state.yaml --template template.yaml --instance instance.yaml
```

### Feed the plan to other tools

`--format json` prints the dry-run plan in a stable schema for CI checks or bots:

```bash
plynth create --template template.yaml --instance instance.yaml --dry-run --format json \
  | jq '.api_call_estimate.total'
```

```text
10
```

The schema and its versioning policy are documented in [docs/dry-run-json.md](docs/dry-run-json.md).

Run `plynth --help` or `plynth create --help` for every command and flag.

## Configuration

### Target

Set `target` in the instance config. It is required.

| Value | Connects to |
| --- | --- |
| `github.com` or `https://api.github.com` | GitHub.com |
| `https://<your-ghes-host>` | GitHub Enterprise Server (GraphQL at `/api/graphql`, REST at `/api/v3`) |

plynth rejects `https://github.com`, `http://` URLs, and bare host names, and tells you which value to use instead.

### Token

plynth reads the token from `PLYNTH_TOKEN`. You can also pass `--token`, but plynth warns that the token then shows up in shell history and process listings.

On GitHub.com, the recommended token is a fine-grained personal access token with these permissions:

- Repository: **Issues** (read and write)
- Organization: **Projects** (read and write)

Classic tokens with the `repo` and `project` scopes work on either target. See [SECURITY.md](SECURITY.md#token-handling) for:

- The full permission breakdown.
- What `repo.create: true` adds.
- The GitHub Enterprise Server 3.19 caveat.

The older `GHES_TOKEN` variable still works but prints a deprecation warning.

### Command options

| Flag | Default | What it does |
| --- | --- | --- |
| `--state-dir` | `.` | Directory for the state file. It must already exist. |
| `--write-delay-ms` | `1000` | Pause between API writes, 0 to 30000 ms (`create` only). |
| `--timeout-seconds` | `30` | Timeout for each HTTP request. |
| `-v`, `--verbose` | off | Debug logging. |

Template features are documented in separate files:

- Single-select options: [docs/options.md](docs/options.md).
- The Status field: [docs/options.md](docs/options.md#status-field).
- Placeholders, milestones, issues, and dependencies: [the annotated example template](docs/example-template.yaml).

## How it works

plynth runs these phases in order and saves the state file after each one:

1. Create the Project and its custom fields.
2. Create repository milestones.
3. Create issues, with their milestones.
4. Add the issues to the Project and set field values.
5. Replace `{PREFIX}-###` references in issue bodies with real issue numbers, and link `blocked_by` and `blocks` dependencies.
6. Create views, when the template opts in (GitHub.com only; see [Status](#status)).
7. Write the final state file.

The architecture and design decisions are in [docs/plynth-design-spec.md](docs/plynth-design-spec.md).

## Status

plynth is in beta (version 0.4.0). GitHub.com is the primary target. A full run has been confirmed against GitHub Enterprise Server 3.19.

plynth only creates new Projects. It does not compare an existing Project with the template, update one, or delete anything.

Known limitations:

- **Views on GitHub Enterprise Server.** Views in a template are documentation only. Set them up in the GitHub UI.
- **Views on GitHub.com.** On the `main` branch, but not in a release yet, `views[].create: true` creates a view's name, layout, and filter. Grouping, sorting, and visible fields are still set in the UI. See [docs/ghec-capabilities.md](docs/ghec-capabilities.md#opt-in-project-views).
- **Custom field types.** plynth creates single-select fields only. The template schema also accepts `text`, `number`, `date`, and `iteration`, but plynth does not create those fields, and it logs a warning and skips any issue values set on them.
- **Multi-select fields.** These are not supported.
- **GitHub App sign-in.** plynth cannot sign in as a GitHub App by itself. To use an app, mint a token yourself and pass it in `PLYNTH_TOKEN`.

Planned work is tracked in the [milestones](https://github.com/Declaratus/plynth/milestones), and changes are listed in the [CHANGELOG](CHANGELOG.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, tests, and the pull request flow. Report security issues privately as described in [SECURITY.md](SECURITY.md).

## License

[Apache-2.0](LICENSE)
