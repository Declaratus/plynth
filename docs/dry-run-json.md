# JSON dry-run output

`plynth create --dry-run --format json` emits the resolved
[`ExecutionPlan`](../plynth/models/plan.py) plus a count of mutating
API calls plynth would make. The shape is stable within a major
`schema_version` so downstream tools (CI plan diffs, bot summaries,
custom dashboards) can pin to it.

## Top-level shape

```json
{
  "schema_version": 1,
  "plynth_version": "0.4.0",
  "plan": { ... },
  "api_call_estimate": { ... }
}
```

| Field               | Type   | Notes                                                                                  |
| ------------------- | ------ | -------------------------------------------------------------------------------------- |
| `schema_version`    | int    | Bumped on breaking shape changes. Additive fields don't change it.                     |
| `plynth_version`    | string | The installed CLI version, from `importlib.metadata.version("plynth")` (`"0.0.0"` if metadata is unavailable). |
| `plan`              | object | The full `ExecutionPlan` (Pydantic `model_dump(mode="json")`).                         |
| `api_call_estimate` | object | Per-category counts plus a `total`; matches the figures in the text dry-run footer.    |

## `plan` block

A direct dump of the `ExecutionPlan` Pydantic model. Today's keys:

- `template_name`, `template_version`
- `instance_org`, `instance_repo`, `instance_repo_create`
- `target` (display: `""` and `"github.com"` are equivalent for the
  github.com target)
- `project_name`, `project_description`
- `status_options` (list of status options)
- `fields` (list of `ResolvedField`: `id`, `name`, `type`,
  `options[].{value,color,description,default}`)
- `milestones` (list of `ResolvedMilestone`)
- `issues` (list of `ResolvedIssue`)
- `views` (list of `ViewDefinition`)
- `placeholder_values` (object: name → resolved value)
- `skipped_milestones`, `skipped_issues` (lists of IDs)
- `warnings` (list of strings)

Adding a new field to `ExecutionPlan` is non-breaking. Renaming or
removing one bumps `schema_version`.

## `api_call_estimate` block

```json
{
  "milestones": 5,
  "issues_create": 17,
  "add_to_project": 17,
  "field_values": 51,
  "body_updates": 17,
  "dependencies": 12,
  "total": 119
}
```

`total` is the sum of the other six. The keys are pinned by a test
(`test_api_call_estimate_keys_and_total`) so accidental renames force
a `schema_version` bump.

## Stability policy

- **Additive change (no bump):** new optional field on `plan` or
  `api_call_estimate`. Consumers that ignore unknown keys keep working.
- **Breaking change (bump `schema_version`):** rename, remove, or
  retype any field; change semantics of an existing field.

Pin to the major `schema_version` you tested against and skip payloads
with a higher one if you can't validate the shape yourself.

## Example consumer

```bash
plynth create --template t.yaml --instance i.yaml --dry-run --format json \
  | jq '.api_call_estimate.total'
```
