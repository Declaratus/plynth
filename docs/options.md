# Field options reference

Single-select field options can be declared in two forms. Both work in the same template; mix as convenient.

## Legacy string form

```yaml
fields:
  - id: workstream
    name: "Workstream"
    type: single_select
    options:
      - "Documentation"
      - "Infrastructure"
      - "Operations"
```

Each option lands on the project board as GRAY with no description. Equivalent to the rich form below with only `value` set.

## Rich object form

```yaml
fields:
  - id: priority
    name: "Priority"
    type: single_select
    allow_unknown_values: false
    options:
      - value: "P1"
        color: RED
        description: "Blocks downstream milestones if it slips."
      - value: "P2"
        color: YELLOW
        description: "Drive to closure within the milestone."
        default: true
      - "P3"                 # mix and match: legacy string form is still valid
```

| key | type | default | notes |
|-----|------|---------|-------|
| `value` | string (max 100) | required | Display name on the board. Placeholders resolved at plan time. |
| `color` | enum | omitted (rendered GRAY) | One of GRAY, BLUE, YELLOW, RED, PURPLE, GREEN, ORANGE, PINK. Anything else fails template validation; add the value to `OptionColor` if a future GHES version introduces a new color. |
| `description` | string (max 2000) | "" | Tooltip text shown on hover in the project board. |
| `default` | bool | false | At most one option per field may be `default: true`. On the `status:` block, controls what new items receive in Phase 4 (see [Status field](#status-field) below). Informational on custom fields until per-issue field defaults land. |
| `aliases` | list[string] | [] | Reserved for future option-rename reconciliation. Currently informational. |
| `deprecated` | bool | false | Marks an option as legacy. Currently informational. |

### Field-level guards

`allow_unknown_values: false` (the default) rejects any issue, template default, or instance override that references a field option value not declared in `options`. Enforcement happens at plan time, so drift fails the run cleanly instead of silently skipping later. Drift in field option taxonomy starts when one issue silently introduces a new value, so the strict default protects views and filters that group on the field. Set `allow_unknown_values: true` only when the field is genuinely free-form (e.g., notes, ad-hoc tags).

## Best practices for option colors

Pick colors per field using the palette as a categorical scale. Avoid two adjacent option values sharing a color. Reuse semantics across fields where possible: red = critical/blocked, gray = neutral/N/A, green = approved/done, yellow = in-progress/attention.

The remaining colors (BLUE, PURPLE, ORANGE, PINK) carry no fixed meaning. Use them for categorical distinctions where the semantics above don't apply.

### Worked example: Status

The reference template's Status field (see `example-template.yaml`) walks the palette so adjacent steps never share a color and the semantic anchors land where you'd expect:

```yaml
status:
  - { value: "Backlog",     color: GRAY,   default: true }  # not yet triaged
  - { value: "Ready",       color: BLUE }                   # categorical
  - { value: "In Progress", color: YELLOW }                 # attention
  - { value: "Blocked",     color: RED }                    # blocked
  - { value: "In Review",   color: PURPLE }                 # categorical
  - { value: "Done",        color: GREEN }                  # done
```

The same mapping carries over to Priority in the reference template (`P1 -- Critical Path` lands on RED, `P2 -- Important` on YELLOW) and to any field with a critical/attention/done axis.

## Status field

The top-level `status:` block configures the project's built-in Status field. It accepts the same option shape as a custom field's `options:`, plus the `default: true` flag selects which option is applied to new items in Phase 4.

```yaml
status:
  - { value: "Triaged",     color: GRAY,   default: true }
  - { value: "Spec'd",      color: BLUE }
  - { value: "In progress", color: YELLOW }
  - { value: "In review",   color: PURPLE }
  - { value: "Done",        color: GREEN }
```

Behavior:

- **Order is preserved.** plynth sends the list in declaration order and GHES 3.19+ honors it (verified end-to-end against the public `updateProjectV2Field` mutation; the in-UI Projects settings flow re-sequences, but the API path does not).
- **Replace, not patch.** plynth overwrites GitHub's defaults (Backlog/Ready/In progress/In review/Done) wholesale. Safe at bootstrap because no items exist on the project yet — see "full-list replacements" below.
- **Default selection.** Mark exactly one option `default: true` to pick what new items receive in Phase 4. If no option is marked, the planner emits a warning and falls back to the first option in display order. Omit the whole `status:` block to keep GitHub's defaults, in which case plynth applies `Backlog` to new items as it always has.
- **GHES floor.** Configurable Status requires GHES 3.19+ (the `singleSelectOptions` field on `UpdateProjectV2FieldInput` shipped in cloud on 2024-12-12). plynth probes the schema at the start of Phase 1 and fails with a clear message on older instances. Templates without a `status:` block run on any GHES version plynth otherwise supports.

## Critical: option mutations are full-list replacements

The ProjectV2 GraphQL mutation that creates or updates field options replaces the full options list. Any option omitted from the input is **deleted**, along with all option-id-bearing field values on items that pointed to it.

plynth's bootstrap path always passes the full declared list, so this is safe at create time. Any future tooling that updates field options on an existing project (reconciliation, rename, deprecation) must read existing options first, merge changes into the full list, then write. Never pass a partial list.
