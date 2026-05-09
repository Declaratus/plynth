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
| `default` | bool | false | At most one option per field may be `default: true`. Reserved for future "set on item creation" behavior; currently informational. |
| `aliases` | list[string] | [] | Reserved for future option-rename reconciliation. Currently informational. |
| `deprecated` | bool | false | Marks an option as legacy. Currently informational. |

### Field-level guards

`allow_unknown_values: false` (the default) rejects any issue, template default, or instance override that references a field option value not declared in `options`. Enforcement happens at plan time, so drift fails the run cleanly instead of silently skipping later. Drift in field option taxonomy starts when one issue silently introduces a new value, so the strict default protects views and filters that group on the field. Set `allow_unknown_values: true` only when the field is genuinely free-form (e.g., notes, ad-hoc tags).

## Best practices for option colors

Pick colors per field as a categorical scale. Avoid two adjacent option values sharing a color, and reuse semantics across fields where possible:

- **red** — critical / blocked / regression
- **yellow** — in progress / attention
- **green** — approved / done
- **gray** — neutral / N/A / not yet triaged
- **blue / purple / orange / pink** — categorical distinctions where the semantics above don't apply

A worked example for a Status field:

```yaml
status:
  - { value: "Backlog",     color: GRAY }
  - { value: "Ready",       color: BLUE }
  - { value: "In Progress", color: YELLOW }
  - { value: "Blocked",     color: RED }
  - { value: "In Review",   color: PURPLE }
  - { value: "Done",        color: GREEN }
```

## Critical: option mutations are full-list replacements

The ProjectV2 GraphQL mutation that creates or updates field options replaces the full options list. Any option omitted from the input is **deleted**, along with all option-id-bearing field values on items that pointed to it.

plynth's bootstrap path always passes the full declared list, so this is safe at create time. Any future tooling that updates field options on an existing project (reconciliation, rename, deprecation) must read existing options first, merge changes into the full list, then write. Never pass a partial list.
