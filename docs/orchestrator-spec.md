# Phase Orchestrator Implementation Spec

## What to build

`plynth/engine/phases.py` — the core orchestration engine that takes an `ExecutionPlan` and drives it through Phases 1–7 using the API clients, checkpointing the `StateFile` after each phase.

`plynth/cli.py` — the CLI entry point that wires everything together.

## Files to create

- `plynth/engine/phases.py` — phase orchestrator
- `plynth/cli.py` — CLI entry point
- `plynth/utils/__init__.py`
- `plynth/utils/references.py` — cross-reference resolution logic (Phase 5 body rewriting)

## Architecture

```
CLI (cli.py)
  │
  ├─ Load YAML files → TemplateDefinition + InstanceConfig
  ├─ Plan (planner.py) → ExecutionPlan
  ├─ If --dry-run: print plan and exit
  ├─ Initialize API clients (api_base, graphql_client, rest_client)
  ├─ Initialize or load StateFile
  └─ Execute phases (phases.py)
       │
       ├─ Phase 1: create_project_and_fields()
       ├─ Phase 2: create_milestones()
       ├─ Phase 3: create_issues()
       ├─ Phase 4: add_items_and_set_fields()
       ├─ Phase 5: resolve_references_and_dependencies()
       ├─ Phase 6: (skip — views not automatable)
       └─ Phase 7: finalize_state()
```

---

## phases.py — PhaseOrchestrator

```python
class PhaseOrchestrator:
    """Executes the plynth phases against GHES, checkpointing state after each."""
    
    def __init__(
        self,
        plan: ExecutionPlan,
        gql: GraphQLClient,
        rest: RESTClient,
        state: StateFile,
        state_path: Path,
        logger: logging.Logger | None = None,
    ):
        self.plan = plan
        self.gql = gql
        self.rest = rest
        self.state = state
        self.state_path = state_path
        self.log = logger or logging.getLogger("plynth")
    
    def execute(self):
        """Run all phases, skipping any already completed (resume support)."""
        phases = [
            (PHASE_1_PROJECT_AND_FIELDS, self.phase_1_create_project_and_fields),
            (PHASE_2_MILESTONES, self.phase_2_create_milestones),
            (PHASE_3_ISSUES, self.phase_3_create_issues),
            (PHASE_4_PROJECT_ITEMS, self.phase_4_add_items_and_set_fields),
            (PHASE_5_REFERENCES, self.phase_5_resolve_references_and_dependencies),
            (PHASE_7_FINALIZE, self.phase_7_finalize),
        ]
        
        for phase_key, phase_fn in phases:
            if self.state.is_phase_complete(phase_key):
                self.log.info(f"Skipping {phase_key} (already complete)")
                continue
            
            self.log.info(f"Starting {phase_key}")
            try:
                phase_fn()
                self.state.mark_phase_complete(phase_key)
                self._save_state()
                self.log.info(f"Completed {phase_key}")
            except Exception as e:
                self.state.mark_phase_error(phase_key, str(e))
                self._save_state()
                self.log.error(f"Failed in {phase_key}: {e}")
                raise
    
    def _save_state(self):
        """Write state file to disk."""
        self.state.touch()
        with open(self.state_path, "w", encoding="utf-8") as f:
            # Use model_dump with mode="json" for clean serialization
            import yaml
            yaml.dump(self.state.model_dump(mode="json"), f, default_flow_style=False, sort_keys=False)
```

### Phase 1: Create Project and Fields

```python
    def phase_1_create_project_and_fields(self):
        """Create project, custom fields, and resolve field/option IDs."""
        
        # 1a. Resolve org and repo IDs
        org_id = self.gql.get_org_id(self.plan.instance_org)
        repo_id = self.gql.get_repo_id(self.plan.instance_org, self.plan.instance_repo)
        self.state.repo = RepoState(name=self.plan.instance_repo, node_id=repo_id)
        
        # 1b. Create the project
        project = self.gql.create_project(org_id, self.plan.project_name)
        self.state.project = ProjectState(
            node_id=project["id"],
            url=project["url"],
            number=project["number"],
        )
        self.log.info(f"Created project: {self.plan.project_name} ({project['url']})")
        
        # 1c. Create custom fields
        for field in self.plan.fields:
            if field.type == "single_select":
                # Build options payload: name + color (use GRAY as default)
                options = [{"name": opt, "color": "GRAY", "description": ""} for opt in field.options]
                self.gql.create_field(
                    project_id=self.state.project.node_id,
                    name=field.name,
                    data_type="SINGLE_SELECT",
                    options=options,
                )
                self.log.info(f"Created field: {field.name} ({len(field.options)} options)")
            # Add other field types here when needed
        
        # 1d. Re-query to get actual field IDs and option IDs
        raw_fields = self.gql.get_project_fields(self.state.project.node_id)
        
        for raw in raw_fields:
            # Match by name to our field definitions
            matching = [f for f in self.plan.fields if f.name == raw["name"]]
            if not matching:
                continue  # Built-in field we didn't create (Status, etc.)
            
            field_def = matching[0]
            options_map = {}
            if "options" in raw:
                for opt in raw["options"]:
                    options_map[opt["name"]] = opt["id"]
            
            self.state.fields[field_def.id] = FieldState(
                node_id=raw["id"],
                options=options_map,
            )
        
        # 1e. Also capture the Status field ID and its option IDs
        for raw in raw_fields:
            if raw.get("name") == "Status":
                options_map = {}
                if "options" in raw:
                    for opt in raw["options"]:
                        options_map[opt["name"]] = opt["id"]
                self.state.status_field_id = raw["id"]
                self.state.fields["_status"] = FieldState(
                    node_id=raw["id"],
                    options=options_map,
                )
                break
```

### Phase 2: Create Milestones

```python
    def phase_2_create_milestones(self):
        """Create repository milestones via REST."""
        
        for ms in self.plan.milestones:
            # Format due_on as ISO 8601 with time component for REST API
            due_on = None
            if ms.due_date:
                due_on = f"{ms.due_date}T00:00:00Z"
            
            result = self.rest.create_milestone(
                owner=self.plan.instance_org,
                repo=self.plan.instance_repo,
                title=ms.title,
                description=ms.description,
                due_on=due_on,
            )
            
            self.state.milestones[ms.id] = MilestoneState(
                number=result["number"],
                node_id=result["node_id"],
                title=result["title"],
            )
            self.log.info(f"Created milestone: {ms.title} (#{result['number']})")
```

### Phase 3: Create Issues

This is the critical phase that captures the template_id → real issue number mapping.

```python
    def phase_3_create_issues(self):
        """Create repository issues via GraphQL with milestone assignment."""
        
        for issue in self.plan.issues:
            # Look up the milestone node_id (not number) for GraphQL createIssue
            milestone_node_id = None
            if issue.milestone_id in self.state.milestones:
                milestone_node_id = self.state.milestones[issue.milestone_id].node_id
            
            result = self.gql.create_issue(
                repository_id=self.state.repo.node_id,
                title=issue.title,
                body=issue.body,  # Still has {PREFIX}-### cross-refs unresolved
                milestone_id=milestone_node_id,
            )
            
            self.state.issues[issue.template_id] = IssueState(
                number=result["number"],
                node_id=result["id"],
                title=result["title"],
                body_sha256=hashlib.sha256(issue.body.encode()).hexdigest(),
            )
            self.log.info(
                f"Created issue #{result['number']}: {result['title']} "
                f"(template_id: {issue.template_id})"
            )
```

### Phase 4: Add Items to Project and Set Field Values

```python
    def phase_4_add_items_and_set_fields(self):
        """Add each issue to the project, then set custom field values."""
        
        for issue in self.plan.issues:
            issue_state = self.state.issues[issue.template_id]
            
            # 4a. Add to project
            item_id = self.gql.add_item_to_project(
                project_id=self.state.project.node_id,
                content_id=issue_state.node_id,
            )
            issue_state.item_id = item_id
            
            # 4b. Set Status to "Backlog"
            if "_status" in self.state.fields:
                status_field = self.state.fields["_status"]
                backlog_option_id = status_field.options.get("Backlog")
                if backlog_option_id:
                    self.gql.set_field_value(
                        project_id=self.state.project.node_id,
                        item_id=item_id,
                        field_id=status_field.node_id,
                        value={"singleSelectOptionId": backlog_option_id},
                    )
            
            # 4c. Set custom field values
            for field_key, option_display_value in issue.fields.items():
                if field_key not in self.state.fields:
                    self.log.warning(f"Field '{field_key}' not found in project fields, skipping")
                    continue
                
                field_state = self.state.fields[field_key]
                option_id = field_state.options.get(option_display_value)
                
                if option_id is None:
                    self.log.warning(
                        f"Option '{option_display_value}' not found for field '{field_key}', skipping"
                    )
                    continue
                
                self.gql.set_field_value(
                    project_id=self.state.project.node_id,
                    item_id=item_id,
                    field_id=field_state.node_id,
                    value={"singleSelectOptionId": option_id},
                )
            
            self.log.info(
                f"Added #{issue_state.number} to project and set {len(issue.fields)} field values"
            )
```

### Phase 5: Resolve Cross-References and Wire Dependencies

This phase does two things:
1. Rewrite issue bodies replacing `{PREFIX}-###` with `#real_number`
2. Call `addBlockedBy` for each dependency edge

```python
    def phase_5_resolve_references_and_dependencies(self):
        """Resolve {PREFIX}-### cross-refs in bodies and wire addBlockedBy edges."""
        
        # 5a. Build the reference map: template_id → real issue number
        # Use the PREFIX from placeholder_values
        prefix = self.plan.placeholder_values.get("PREFIX", "")
        
        ref_map = {}  # "{PREFIX}-001" → "#47"
        for template_id, issue_state in self.state.issues.items():
            ref_key = f"{prefix}-{template_id}"
            ref_map[ref_key] = f"#{issue_state.number}"
        
        # 5b. Rewrite each issue body
        for issue in self.plan.issues:
            issue_state = self.state.issues[issue.template_id]
            
            resolved_body = resolve_crossrefs(
                body=issue.body,
                ref_map=ref_map,
                skipped_refs=self._build_skipped_ref_set(issue, prefix),
            )
            
            if resolved_body != issue.body:
                self.gql.update_issue_body(issue_state.node_id, resolved_body)
                issue_state.body_sha256 = hashlib.sha256(resolved_body.encode()).hexdigest()
                self.log.info(f"Resolved cross-refs in #{issue_state.number}")
        
        # 5c. Wire dependency edges via addBlockedBy
        for issue in self.plan.issues:
            issue_state = self.state.issues[issue.template_id]
            
            # blocked_by: this issue is blocked by target
            for blocker_id in issue.blocked_by:
                if blocker_id not in self.state.issues:
                    continue  # skipped issue, already warned
                blocker_state = self.state.issues[blocker_id]
                
                self.gql.add_blocked_by(
                    issue_id=issue_state.node_id,
                    blocking_issue_id=blocker_state.node_id,
                )
                self.state.dependencies_created.append(
                    DependencyEdge(blocker=blocker_id, blocked=issue.template_id)
                )
            
            # blocks: target is blocked by this issue
            for blocked_id in issue.blocks:
                if blocked_id not in self.state.issues:
                    continue
                blocked_state = self.state.issues[blocked_id]
                
                # Check if already created from the other direction
                edge = DependencyEdge(blocker=issue.template_id, blocked=blocked_id)
                if edge not in self.state.dependencies_created:
                    self.gql.add_blocked_by(
                        issue_id=blocked_state.node_id,
                        blocking_issue_id=issue_state.node_id,
                    )
                    self.state.dependencies_created.append(edge)
            
            dep_count = len(issue.blocked_by) + len(issue.blocks)
            if dep_count > 0:
                self.log.info(f"Wired {dep_count} dependencies for #{issue_state.number}")
    
    def _build_skipped_ref_set(self, issue: ResolvedIssue, prefix: str) -> set[str]:
        """Build set of {PREFIX}-### strings for skipped dependencies."""
        skipped = set()
        for tid in issue.skipped_blocked_by + issue.skipped_blocks:
            skipped.add(f"{prefix}-{tid}")
        return skipped
```

### Phase 7: Finalize

```python
    def phase_7_finalize(self):
        """Mark the run as complete and write final state."""
        self.state.skipped = SkippedItems(
            milestones=self.plan.skipped_milestones,
            issues=self.plan.skipped_issues,
        )
        self.log.info(
            f"Bootstrap complete. Project: {self.state.project.url}\n"
            f"  Issues created: {len(self.state.issues)}\n"
            f"  Milestones created: {len(self.state.milestones)}\n"
            f"  Dependencies wired: {len(self.state.dependencies_created)}"
        )
```

---

## utils/references.py — Cross-Reference Resolution

```python
import re

def resolve_crossrefs(body: str, ref_map: dict[str, str], skipped_refs: set[str]) -> str:
    """Replace {PREFIX}-### patterns in body text with #real_number or strikethrough.
    
    ref_map: {"EX-001": "#47", "EX-002": "#48", ...}
    skipped_refs: {"EX-006", "EX-007", ...}  — refs that were skipped
    
    Matching pattern: looks for keys from ref_map and skipped_refs in the body text.
    We match word-boundary-delimited patterns to avoid partial matches.
    """
    
    # Build a combined pattern from all known refs
    all_refs = set(ref_map.keys()) | skipped_refs
    if not all_refs:
        return body
    
    # Sort longest first to avoid partial matches
    sorted_refs = sorted(all_refs, key=len, reverse=True)
    # Escape for regex and join with |
    pattern = re.compile(
        r'(?<!\w)(' + '|'.join(re.escape(ref) for ref in sorted_refs) + r')(?!\w)'
    )
    
    def replace_match(match):
        ref = match.group(1)
        if ref in skipped_refs:
            return f"~~{ref}~~ (skipped)"
        if ref in ref_map:
            return ref_map[ref]
        return ref  # shouldn't happen
    
    return pattern.sub(replace_match, body)
```

---

## cli.py — CLI Entry Point

```python
"""plynth CLI — GitHub Projects as Code."""

import argparse
import hashlib
import logging
import sys
from pathlib import Path

import yaml

from plynth.models.template import TemplateDefinition
from plynth.models.instance import InstanceConfig
from plynth.models.state import StateFile
from plynth.engine.planner import plan, format_dry_run
from plynth.engine.api_base import GHESClient
from plynth.engine.graphql_client import GraphQLClient
from plynth.engine.rest_client import RESTClient
from plynth.engine.phases import PhaseOrchestrator


def main():
    parser = argparse.ArgumentParser(
        prog="plynth",
        description="GitHub Projects as Code — bootstrap GitHub Projects from YAML templates.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # --- create command ---
    create_parser = subparsers.add_parser("create", help="Create a new project from template")
    create_parser.add_argument("--template", required=True, help="Path to template YAML")
    create_parser.add_argument("--instance", required=True, help="Path to instance config YAML")
    create_parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    create_parser.add_argument("--token", help="GHES PAT (or set GHES_TOKEN env var)")
    create_parser.add_argument("--state-dir", default=".", help="Directory for state file output")
    create_parser.add_argument("--write-delay-ms", type=int, default=1000, help="Delay between API writes (ms)")
    create_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    
    # --- resolve command ---
    resolve_parser = subparsers.add_parser("resolve", help="Re-resolve cross-references from state file")
    resolve_parser.add_argument("--state", required=True, help="Path to existing state file")
    resolve_parser.add_argument("--template", required=True, help="Path to template YAML")
    resolve_parser.add_argument("--instance", required=True, help="Path to instance config YAML")
    resolve_parser.add_argument("--token", help="GHES PAT (or set GHES_TOKEN env var)")
    resolve_parser.add_argument("-v", "--verbose", action="store_true")
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("plynth")
    
    if args.command == "create":
        _cmd_create(args, log)
    elif args.command == "resolve":
        _cmd_resolve(args, log)


def _cmd_create(args, log):
    """Execute the 'create' command."""
    
    # 1. Load and parse YAML
    template = _load_template(args.template)
    instance = _load_instance(args.instance)
    
    # 2. Plan
    execution_plan = plan(template, instance)
    
    # 3. Dry run?
    if args.dry_run:
        print(format_dry_run(execution_plan))
        return
    
    # 4. Get token
    token = _get_token(args)
    
    # 5. Initialize clients
    base = GHESClient(instance.ghes_url, token, write_delay_ms=args.write_delay_ms)
    gql = GraphQLClient(base)
    rest = RESTClient(base)
    
    # 6. Initialize or resume state file
    state_path = Path(args.state_dir) / f"{_slugify(execution_plan.project_name)}.plynth-state.yaml"
    state = _init_or_load_state(state_path, args.template, args.instance, instance, log)
    
    # 7. Execute
    orchestrator = PhaseOrchestrator(
        plan=execution_plan,
        gql=gql,
        rest=rest,
        state=state,
        state_path=state_path,
        logger=log,
    )
    orchestrator.execute()
    
    log.info(f"State file written to: {state_path}")


def _cmd_resolve(args, log):
    """Execute the 'resolve' command — re-run Phase 5 only."""
    
    template = _load_template(args.template)
    instance = _load_instance(args.instance)
    execution_plan = plan(template, instance)
    
    token = _get_token(args)
    base = GHESClient(instance.ghes_url, token)
    gql = GraphQLClient(base)
    rest = RESTClient(base)  # Not used but needed for orchestrator init
    
    # Load existing state
    state = _load_state(Path(args.state))
    
    # Reset Phase 5 so it re-runs
    from plynth.models.state import PHASE_5_REFERENCES
    state.phases.pop(PHASE_5_REFERENCES, None)
    
    orchestrator = PhaseOrchestrator(
        plan=execution_plan, gql=gql, rest=rest,
        state=state, state_path=Path(args.state), logger=log,
    )
    # Only run Phase 5
    orchestrator.phase_5_resolve_references_and_dependencies()
    state.mark_phase_complete(PHASE_5_REFERENCES)
    orchestrator._save_state()
    log.info("Re-resolve complete.")


def _load_template(path: str) -> TemplateDefinition:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return TemplateDefinition.model_validate(data)


def _load_instance(path: str) -> InstanceConfig:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return InstanceConfig.model_validate(data)


def _load_state(path: Path) -> StateFile:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return StateFile.model_validate(data)


def _get_token(args) -> str:
    import os
    token = getattr(args, "token", None) or os.environ.get("GHES_TOKEN")
    if not token:
        print("Error: provide --token or set GHES_TOKEN environment variable.", file=sys.stderr)
        sys.exit(1)
    return token


def _init_or_load_state(
    state_path: Path, 
    template_path: str, 
    instance_path: str, 
    instance: InstanceConfig,
    log: logging.Logger,
) -> StateFile:
    """Initialize a new state file or load existing one for resume."""
    
    template_hash = _file_hash(template_path)
    instance_hash = _file_hash(instance_path)
    
    if state_path.exists():
        log.info(f"Found existing state file: {state_path}")
        state = _load_state(state_path)
        
        # Guard: template hash must match for resume
        if state.template_sha256 and state.template_sha256 != template_hash:
            print(
                f"Error: template has changed since the state file was created.\n"
                f"  State template hash:   {state.template_sha256}\n"
                f"  Current template hash: {template_hash}\n"
                f"Delete the state file to start fresh, or use a new state directory.",
                file=sys.stderr,
            )
            sys.exit(1)
        
        return state
    
    # New state file
    from plynth.models.state import TemplateRef, InstanceRef, RepoState
    from datetime import datetime, timezone
    
    state = StateFile(
        created_at=datetime.now(timezone.utc).isoformat(),
        template_sha256=template_hash,
        instance_sha256=instance_hash,
        template=TemplateRef(file=template_path, version=""),
        instance=InstanceRef(file=instance_path, config_hash=instance_hash),
        ghes_url=instance.ghes_url,
        org=instance.org,
        repo=RepoState(name=instance.repo.name),
    )
    return state


def _file_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _slugify(text: str) -> str:
    """Convert project name to filesystem-safe slug."""
    import re
    slug = text.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug
```

---

## Dependency deduplication in Phase 5

The dependency graph has both `blocked_by` and `blocks` arrays that are bidirectional mirrors. When the planner resolves them, issue A has `blocks: ["B"]` and issue B has `blocked_by: ["A"]`. Both describe the same edge: B is blocked by A.

Phase 5 must only call `addBlockedBy` ONCE per edge, not twice. The logic:

```
For each issue:
    For each blocked_by ref → addBlockedBy(self, blocker) → record edge (blocker→self)
    For each blocks ref → addBlockedBy(target, self) → BUT only if edge not already recorded

Check: DependencyEdge(blocker=X, blocked=Y) already in state.dependencies_created?
    If yes, skip (already wired from the other issue's blocked_by pass)
    If no, create it
```

This is why `DependencyEdge` has both `blocker` and `blocked` fields and why we check before calling.

---

## Resume behavior

The state file is checkpointed after each phase. On re-run:

- Phase 1 complete? Skip it (project and fields already exist)
- Phase 2 complete? Skip it (milestones already exist)
- Phase 3 complete? Skip it (issues already created, mapping captured)
- etc.

The `template_sha256` guard prevents resuming with a different template. If someone changes the template after Phase 3 but before Phase 5, they get an error telling them to delete the state file and start fresh. This is the right behavior for bootstrap-only mode.

---

## Testing

Since this talks to a real GHES instance, full integration testing requires a live server. For the initial build:

1. Verify all files import cleanly
2. Verify `PhaseOrchestrator` can be instantiated with mock objects
3. Verify `resolve_crossrefs()` in `utils/references.py` works:
   ```python
   body = "Depends on: {PREFIX}-001, {PREFIX}-006\nBlocks: {PREFIX}-002"
   ref_map = {"EX-001": "#47", "EX-002": "#48"}
   skipped = {"EX-006"}
   result = resolve_crossrefs(body, ref_map, skipped)
   assert "#47" in result
   assert "#48" in result
   assert "~~EX-006~~ (skipped)" in result
   ```
4. Verify CLI parses args correctly:
   ```
   plynth create --template t.yaml --instance i.yaml --dry-run
   plynth create --template t.yaml --instance i.yaml --token fake
   plynth resolve --state s.yaml --template t.yaml --instance i.yaml --token fake
   ```
5. Verify `_slugify()` produces clean filenames:
   ```python
   assert _slugify("Example Vendor -- Operational Maturity") == "example-vendor-tos---operational-maturity"
   ```

## Important notes

- Always `encoding='utf-8'` on all file I/O
- Phase 5 body resolution uses `{PREFIX}-###` where PREFIX is the resolved value (e.g., "EX"), not the placeholder token. The planner already resolved `{PREFIX}` in titles but preserved `{PREFIX}-###` in bodies. Wait — actually the planner preserves the literal `{PREFIX}-###` token. So the ref_map keys need to use the resolved prefix value. Double-check: in the planner, bodies still have the literal string `{PREFIX}-001` (the curly braces are preserved). The reference resolver needs to handle whichever format the planner outputs. Look at the planner's `resolve_placeholders()` with `preserve_crossrefs=True` to see exactly what token format remains in the body.
- The `_cmd_resolve` function resets Phase 5 and re-runs it. It does NOT re-run Phases 1-4. It reads issue node_ids from the existing state file.
