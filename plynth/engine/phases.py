"""Phase orchestrator — drives Phases 1-7 against GHES."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import yaml

from plynth.engine.graphql_client import GraphQLClient
from plynth.engine.rest_client import RESTClient
from plynth.errors import NotFoundError, PlynthError
from plynth.models.plan import ExecutionPlan, ResolvedIssue
from plynth.models.state import (
    PHASE_1_PROJECT_AND_FIELDS,
    PHASE_2_MILESTONES,
    PHASE_3_ISSUES,
    PHASE_4_PROJECT_ITEMS,
    PHASE_5_REFERENCES_AND_DEPS,
    PHASE_7_STATE_FILE,
    DependencyEdge,
    FieldState,
    IssueState,
    MilestoneState,
    ProjectState,
    RepoState,
    SkippedItems,
    StateFile,
)
from plynth.utils.references import resolve_crossrefs


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
    ) -> None:
        self.plan = plan
        self.gql = gql
        self.rest = rest
        self.state = state
        self.state_path = state_path
        self.log = logger or logging.getLogger("plynth")

    def execute(self) -> None:
        """Run all phases, skipping any already completed (resume support)."""
        phases = [
            (PHASE_1_PROJECT_AND_FIELDS, self.phase_1_create_project_and_fields),
            (PHASE_2_MILESTONES, self.phase_2_create_milestones),
            (PHASE_3_ISSUES, self.phase_3_create_issues),
            (PHASE_4_PROJECT_ITEMS, self.phase_4_add_items_and_set_fields),
            (
                PHASE_5_REFERENCES_AND_DEPS,
                self.phase_5_resolve_references_and_dependencies,
            ),
            (PHASE_7_STATE_FILE, self.phase_7_finalize),
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
            except PlynthError as e:
                # User-facing failure: message is already friendly. Record
                # cleanly so a resume can show what went wrong.
                self.state.mark_phase_error(phase_key, str(e))
                self._save_state()
                self.log.error(f"Failed in {phase_key}: {e}")
                raise
            except Exception as e:
                # Unhandled error (programming bug, third-party library
                # crash). Prefix the class name on the state marker so an
                # operator inspecting the state file can tell internal
                # failures from user-facing ones, and log with traceback
                # since the message alone may not be enough to diagnose.
                self.state.mark_phase_error(phase_key, f"{type(e).__name__}: {e}")
                self._save_state()
                self.log.exception(f"Unhandled error in {phase_key}")
                raise

    def _save_state(self) -> None:
        """Write state file to disk."""
        self.state.touch()
        with open(self.state_path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.state.model_dump(mode="json"),
                f,
                default_flow_style=False,
                sort_keys=False,
            )

    # ── Phase 1: Create Project and Fields ─────────────────

    def phase_1_create_project_and_fields(self) -> None:
        """Create project, custom fields, and resolve field/option IDs."""

        # 1a. Resolve org and repo IDs
        org_id = self.gql.get_org_id(self.plan.instance_org)
        repo_id = self._resolve_repo_id()
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
                options = [
                    {"name": opt.value, "color": opt.color, "description": opt.description}
                    for opt in field.options
                ]
                self.gql.create_field(
                    project_id=self.state.project.node_id,
                    name=field.name,
                    data_type="SINGLE_SELECT",
                    options=options,
                )
                self.log.info(f"Created field: {field.name} ({len(field.options)} options)")

        # 1d. Re-query to get actual field IDs and option IDs
        raw_fields = self.gql.get_project_fields(self.state.project.node_id)

        for raw in raw_fields:
            matching = [f for f in self.plan.fields if f.name == raw.get("name")]
            if not matching:
                # Check for Status built-in field
                if raw.get("name") == "Status":
                    options_map = {}
                    if "options" in raw:
                        for opt in raw["options"]:
                            options_map[opt["name"]] = opt["id"]
                    self.state.status_field_id = raw["id"]
                    self.state.fields["_status"] = FieldState(
                        node_id=raw["id"], options=options_map
                    )
                continue

            field_def = matching[0]
            options_map = {}
            if "options" in raw:
                for opt in raw["options"]:
                    options_map[opt["name"]] = opt["id"]

            self.state.fields[field_def.id] = FieldState(node_id=raw["id"], options=options_map)

    def _resolve_repo_id(self) -> str:
        """Look up the repo node ID, creating the repo first if configured.

        With `repo.create: false` (default), a missing repo raises NotFoundError
        as before. With `repo.create: true`, plynth creates the repo (private)
        via REST and re-resolves. An already-existing repo is a no-op either way.
        """
        org = self.plan.instance_org
        name = self.plan.instance_repo
        try:
            return self.gql.get_repo_id(org, name)
        except NotFoundError:
            if not self.plan.instance_repo_create:
                raise
            self.log.info(f"Repository {org}/{name} not found, creating (repo.create=true)")
            self.rest.create_repo(org, name)
            return self.gql.get_repo_id(org, name)

    # ── Phase 2: Create Milestones ─────────────────────────

    def phase_2_create_milestones(self) -> None:
        """Create repository milestones via REST."""
        for ms in self.plan.milestones:
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

    # ── Phase 3: Create Issues ─────────────────────────────

    def phase_3_create_issues(self) -> None:
        """Create repository issues via GraphQL with milestone assignment."""
        for issue in self.plan.issues:
            milestone_node_id = None
            if issue.milestone_id in self.state.milestones:
                milestone_node_id = self.state.milestones[issue.milestone_id].node_id

            result = self.gql.create_issue(
                repository_id=self.state.repo.node_id,
                title=issue.title,
                body=issue.body,
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

    # ── Phase 4: Add Items to Project + Set Fields ─────────

    def phase_4_add_items_and_set_fields(self) -> None:
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
                        f"Option '{option_display_value}' not found for "
                        f"field '{field_key}', skipping"
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

    # ── Phase 5: Resolve Cross-References + Dependencies ───

    def phase_5_resolve_references_and_dependencies(self) -> None:
        """Resolve {PREFIX}-### cross-refs in bodies and wire addBlockedBy edges."""

        # 5a. Build the reference map: "{PREFIX}-001" → "#47"
        # The planner preserves literal {PREFIX}-### in bodies (curly braces
        # intact), so ref_map keys must use the same literal format.
        ref_map: dict[str, str] = {}
        for template_id, issue_state in self.state.issues.items():
            ref_key = f"{{PREFIX}}-{template_id}"
            ref_map[ref_key] = f"#{issue_state.number}"

        # 5b. Rewrite each issue body
        for issue in self.plan.issues:
            issue_state = self.state.issues[issue.template_id]

            resolved_body = resolve_crossrefs(
                body=issue.body,
                ref_map=ref_map,
                skipped_refs=self._build_skipped_ref_set(issue),
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
                    continue

                edge = DependencyEdge(blocker=blocker_id, blocked=issue.template_id)
                if edge in self.state.dependencies_created:
                    continue  # already wired earlier via blocks/blocked_by elsewhere

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

                # Deduplicate: skip if already created from the other direction
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

    def _build_skipped_ref_set(self, issue: ResolvedIssue) -> set[str]:
        """Build set of {PREFIX}-### strings for skipped dependencies."""
        skipped: set[str] = set()
        for tid in issue.skipped_blocked_by + issue.skipped_blocks:
            skipped.add(f"{{PREFIX}}-{tid}")
        return skipped

    # ── Phase 7: Finalize ──────────────────────────────────

    def phase_7_finalize(self) -> None:
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
