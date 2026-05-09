# Planner Implementation Spec

## What to build

`plynth/engine/planner.py` — the pre-flight engine that takes a template + instance config and produces a fully resolved execution plan. No API calls. Pure computation.

## Files to create

- `plynth/engine/__init__.py`
- `plynth/engine/planner.py`

## What the planner does

The planner is the bridge between "human-authored YAML" and "ready to send to GitHub." It takes the raw parsed models (TemplateDefinition + InstanceConfig), applies all the business logic (skipping, pruning, placeholder resolution, dependency validation), and outputs a resolved execution plan that the API phases consume directly.

### Core function signature

```python
def plan(template: TemplateDefinition, instance: InstanceConfig) -> ExecutionPlan:
```

### ExecutionPlan model

Add to `plynth/models/plan.py`:

```python
class ResolvedIssue(BaseModel):
    """An issue with all placeholders resolved, ready for API submission."""
    template_id: str
    title: str                    # Placeholders resolved
    body: str                     # Placeholders resolved EXCEPT {PREFIX}-### cross-refs
    milestone_id: str             # References a key in resolved_milestones
    fields: dict[str, str]        # field_id -> option display value (placeholders resolved)
    blocked_by: list[str]         # template_ids (only valid/non-skipped targets)
    blocks: list[str]             # template_ids (only valid/non-skipped targets)
    skipped_blocked_by: list[str] # template_ids that were in original but got skipped
    skipped_blocks: list[str]     # template_ids that were in original but got skipped

class ResolvedMilestone(BaseModel):
    """A milestone with placeholders resolved and due date calculated."""
    id: str
    title: str
    description: str
    due_date: str | None = None   # ISO date string, calculated from start_date + offset

class ResolvedField(BaseModel):
    """A field with placeholder-resolved options."""
    id: str
    name: str
    type: str
    options: list[str]            # Placeholders resolved in option values

class ExecutionPlan(BaseModel):
    """The complete resolved plan, ready for API execution."""
    model_config = ConfigDict(extra="forbid")
    
    # Metadata
    template_name: str
    template_version: str
    instance_org: str
    instance_repo: str
    ghes_url: str
    project_name: str
    project_description: str
    
    # Resolved resources
    status_options: list[ResolvedFieldOption]  # From template, placeholder-resolved (drives updateProjectV2Field on system Status)
    fields: list[ResolvedField]
    milestones: list[ResolvedMilestone]
    issues: list[ResolvedIssue]
    views: list[ViewDefinition]             # From template, unchanged (documentation only)
    
    # Placeholder values used (for audit trail)
    placeholder_values: dict[str, str]
    
    # Skip/prune summary
    skipped_milestones: list[str]
    skipped_issues: list[str]               # All skipped issue template_ids (from milestones + individual + pruning)
    
    # Warnings
    warnings: list[str]                     # Orphaned deps, skipped refs, etc.
```

## Planner logic — step by step

### Step 1: Validate placeholder coverage

```
For each placeholder in template.placeholders where required=True:
    assert placeholder key exists in instance.values
    assert value is non-empty string
Fail fast with clear error message listing missing placeholders.
```

### Step 2: Compute effective milestone list

```
effective_milestones = []
for milestone in template.milestones:
    if milestone.id in instance.skip_milestones:
        continue  # skipped
    resolved = ResolvedMilestone(
        id=milestone.id,
        title=resolve_placeholders(milestone.title, instance.values),
        description=resolve_placeholders(milestone.description, instance.values),
        due_date=calculate_due_date(instance.start_date, milestone.due_offset_weeks)
    )
    effective_milestones.append(resolved)
```

### Step 3: Compute effective issue list

Three sources of exclusion applied in order:

```
skipped_by_milestone = set of template_ids whose milestone_id is in skip_milestones
skipped_individually = set of template_ids in instance.skip_issues  
skipped_by_pruning = set()  # empty unless pruning_decision is set

If instance.pruning_decision is set AND template.pruning exists:
    Find the matching rule by field_value
    skipped_by_pruning = set(rule.remove_issues)

all_skipped = skipped_by_milestone | skipped_individually | skipped_by_pruning
effective_issues = [i for i in template.issues if i.template_id not in all_skipped]
```

### Step 4: Resolve placeholders in effective issues

For each effective issue:
- Resolve `{VENDOR}`, `{PREFIX}`, `{PLATFORM}`, etc. in title
- Resolve same in body — BUT leave `{PREFIX}-###` cross-reference patterns UNRESOLVED
  (those get resolved in Phase 5 at runtime when real issue numbers are known)
- Resolve placeholders in field option values (e.g., `"Vendor ({VENDOR})"` → `"Vendor (Example Vendor)"`)
- Apply field_overrides from instance config if any match this issue's template_id

The cross-reference preservation is critical. The regex pattern to NOT resolve:
```python
# Resolve {PREFIX} everywhere EXCEPT when followed by -### (3 digits)
# Strategy: temporarily replace {PREFIX}-### patterns, resolve all placeholders, restore them.
import re

CROSSREF_PATTERN = re.compile(r'\{PREFIX\}-(\d{3})')

def resolve_placeholders(text: str, values: dict[str, str], preserve_crossrefs: bool = False) -> str:
    if preserve_crossrefs and 'PREFIX' in values:
        # Save cross-references
        saved = {}
        def save(match):
            key = f"__CROSSREF_{match.group(1)}__"
            saved[key] = match.group(0)
            return key
        text = CROSSREF_PATTERN.sub(save, text)
    
    # Resolve all {KEY} patterns
    for key, value in values.items():
        text = text.replace(f"{{{key}}}", value)
    
    if preserve_crossrefs:
        # Restore cross-references
        for key, original in saved.items():
            text = text.replace(key, original)
    
    return text
```

Call with `preserve_crossrefs=True` for issue bodies, `False` for titles and field options.

Wait — titles also have `{PREFIX}-001:` format. Those SHOULD be resolved since the title needs to show `GOV-001:` or `EX-001:`. The `{PREFIX}-###` preservation is body-only.

Correction: resolve all placeholders in titles (no preservation). In bodies, preserve `{PREFIX}-###` patterns only.

### Step 5: Validate and trim dependency graph

For each effective issue:
```
valid_ids = set of template_ids in effective_issues
warnings = []

for issue in effective_issues:
    resolved_blocked_by = []
    skipped_blocked_by = []
    for ref in issue.blocked_by:
        if ref in valid_ids:
            resolved_blocked_by.append(ref)
        else:
            skipped_blocked_by.append(ref)
            warnings.append(f"Issue {issue.template_id}: blocked_by ref '{ref}' was skipped (milestone excluded or individually skipped)")
    
    # Same for blocks
    resolved_blocks = []
    skipped_blocks = []
    for ref in issue.blocks:
        if ref in valid_ids:
            resolved_blocks.append(ref)
        else:
            skipped_blocks.append(ref)
            warnings.append(f"Issue {issue.template_id}: blocks ref '{ref}' was skipped")
```

Store both `resolved_*` and `skipped_*` lists on ResolvedIssue. The skipped lists are used in Phase 5 for strikethrough treatment in body text.

### Step 6: Resolve field options with placeholders

For each field definition:
```
resolved_options = [resolve_placeholders(opt, instance.values) for opt in field.options]
```

This handles `"Vendor ({VENDOR})"` → `"Vendor (Example Vendor)"`.

### Step 7: Calculate milestone due dates

```python
from datetime import date, timedelta

def calculate_due_date(start_date_str: str | None, offset_weeks: int) -> str | None:
    if start_date_str is None:
        return None
    start = date.fromisoformat(start_date_str)
    due = start + timedelta(weeks=offset_weeks)
    return due.isoformat()
```

### Step 8: Resolve project description

The instance config project description may contain `{DATE}`:
```python
from datetime import date
description = instance.project.description.replace("{DATE}", date.today().isoformat())
```

### Step 9: Assemble and return ExecutionPlan

Bundle everything into the ExecutionPlan model and return it.

## Dry run output

Add a `format_dry_run(plan: ExecutionPlan) -> str` function that prints a human-readable summary:

```
=== plynth Execution Plan ===
Template: Managed Service Cluster -- Operational Maturity (v3)
Target:   https://ghes.example.com / example-org / example-repo
Project:  Example Vendor -- Operational Maturity

Milestones (4):
  M1: M1: Documentation & Inventory Foundation (due: 2026-04-06)
  M3: M3: Operational Visibility (due: 2026-05-11)
  M4: M4: Compliance & Security (due: 2026-06-22)
  M5: M5: Resilience & Integrations (due: 2026-07-06)

Skipped milestones: M2
Skipped issues (4): 005, 006, 007, 008

Issues (14):
  001: EX-001: Create vendor repo from docs template [M1] [P1]
       blocked_by: (none) | blocks: 002
  002: EX-002: Configure and publish GitHub Pages doc site [M1] [P1]
       blocked_by: 001 | blocks: (none)
  003: EX-003: Document current-state architecture and configuration [M1] [P1]
       blocked_by: (none) | blocks: ~~006~~ (skipped)
  ...

Fields (4):
  workstream: Workstream [single_select] (5 options)
  capability: Capability [single_select] (6 options)
  priority: Priority [single_select] (3 options)
  requires_external: Requires External [single_select] (4 options)
    → "Vendor (Example Vendor)" (placeholder resolved)

Warnings (3):
  ⚠ Issue 003: blocks ref '006' was skipped (milestone excluded)
  ⚠ Issue 009: blocked_by ref '006' was skipped (milestone excluded)
  ⚠ Issue 010: blocked_by ref '006' was skipped (milestone excluded)

API call estimate:
  Milestones:  4 REST calls
  Issues:      14 GraphQL createIssue calls
  Add to project: 14 GraphQL addProjectV2ItemById calls
  Field values: 56 GraphQL updateProjectV2ItemFieldValue calls (14 issues × 4 fields)
  Body updates: 14 GraphQL updateIssue calls (cross-ref resolution)
  Dependencies: ~X GraphQL addBlockedBy calls
  Total: ~X mutating calls (~X seconds at 1s delay)
```

## Test cases

After building the planner, verify with:

1. **Vendor cluster + Example Vendor instance (M2 skipped)**
   - 14 effective issues (18 - 4 from M2)
   - 4 effective milestones
   - Warnings for orphaned deps on 006 (blocked_by from 003, 009, 010, 016)
   - Placeholder resolution: `{VENDOR}` → `Example Vendor`, `{PREFIX}` → `EX`, `{PLATFORM}` → `kubernetes`
   - Field option: `"Vendor ({VENDOR})"` → `"Vendor (Example Vendor)"`

2. **Governance workflow + governance instance (nothing skipped)**
   - 57 effective issues (no skips)
   - 5 effective milestones
   - Zero warnings
   - Placeholder resolution: `{PREFIX}` → `GOV`
   - No field option placeholders to resolve

3. **Vendor cluster + Example Vendor instance, dry run output**
   - Verify human-readable output matches expected format
   - Verify API call estimate math

## Important: encoding

Always open YAML files with `encoding='utf-8'`. Windows default cp1252 chokes on em-dashes in the templates.
