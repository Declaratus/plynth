from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TemplateRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    version: str


class InstanceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    config_hash: str


class RepoState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    node_id: str = ""


class ProjectState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = ""
    url: str = ""
    number: int = 0


class FieldState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    options: dict[str, str] = {}


class MilestoneState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int
    node_id: str
    title: str


class IssueState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int
    node_id: str
    item_id: str = ""
    title: str
    body_sha256: str = ""


class DependencyEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocker: str
    blocked: str


class SkippedItems(BaseModel):
    model_config = ConfigDict(extra="forbid")

    milestones: list[str] = []
    issues: list[str] = []


class PhaseStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completed: bool = False
    completed_at: str | None = None
    error: str | None = None


# Canonical phase key constants.
PHASE_1_PROJECT_AND_FIELDS = "phase_1_project_and_fields"
PHASE_2_MILESTONES = "phase_2_milestones"
PHASE_3_ISSUES = "phase_3_issues"
PHASE_4_PROJECT_ITEMS = "phase_4_project_items"
PHASE_5_REFERENCES_AND_DEPS = "phase_5_references_and_deps"
PHASE_7_STATE_FILE = "phase_7_state_file"


class StateFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _apply_compat_shims(cls, data: Any) -> Any:
        """Single funnel for state-file shape migrations across schema_version.

        State files are machine-written, so a hard schema rename would break
        in-flight resume across a plynth upgrade. This hook owns every dict
        transformation needed to upgrade an older state file into the current
        in-memory shape. Pydantic field defaults handle zero-filling missing
        keys; this hook is for renames, relocations, and structural changes
        that defaults can't express.

        Shims, oldest first:

        - pre-v0.3 (``ghes_url`` key): renamed to ``target`` in v0.3. The new
          ``target`` key wins if both are somehow present.

        See ``docs/plynth-design-spec.md#schema-versioning`` for the cadence
        and which schema_version each shim corresponds to.
        """
        if not isinstance(data, dict):
            return data
        data = {**data}

        # pre-v0.3 → v0.3+: ghes_url renamed to target. setdefault preserves
        # any explicit target= that's already present.
        if "ghes_url" in data:
            legacy = data.pop("ghes_url")
            data.setdefault("target", legacy)

        return data

    schema_version: str = "1.0"
    created_at: str = ""
    updated_at: str = ""
    template_sha256: str = ""
    instance_sha256: str = ""
    template: TemplateRef | None = None
    instance: InstanceRef | None = None
    target: str = ""
    org: str = ""
    repo: RepoState | None = None
    project: ProjectState | None = None
    fields: dict[str, FieldState] = {}
    status_field_id: str | None = None
    milestones: dict[str, MilestoneState] = {}
    issues: dict[str, IssueState] = {}
    dependencies_created: list[DependencyEdge] = []
    skipped: SkippedItems = Field(default_factory=SkippedItems)
    phases: dict[str, PhaseStatus] = {}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def touch(self) -> None:
        self.updated_at = self._now_iso()

    def mark_phase_complete(self, phase: str) -> None:
        self.phases[phase] = PhaseStatus(completed=True, completed_at=self._now_iso())
        self.touch()

    def mark_phase_error(self, phase: str, error: str) -> None:
        existing = self.phases.get(phase, PhaseStatus())
        existing.error = error
        self.phases[phase] = existing
        self.touch()

    def is_phase_complete(self, phase: str) -> bool:
        status = self.phases.get(phase)
        return status is not None and status.completed
