from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from plynth.models.template import StatusOption, ViewDefinition


class ResolvedIssue(BaseModel):
    """An issue with all placeholders resolved, ready for API submission."""

    model_config = ConfigDict(extra="forbid")

    template_id: str
    title: str
    body: str
    milestone_id: str
    fields: dict[str, str]
    blocked_by: list[str]
    blocks: list[str]
    skipped_blocked_by: list[str]
    skipped_blocks: list[str]


class ResolvedMilestone(BaseModel):
    """A milestone with placeholders resolved and due date calculated."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str
    due_date: str | None = None


class ResolvedField(BaseModel):
    """A field with placeholder-resolved options."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: str
    options: list[str]


class ExecutionPlan(BaseModel):
    """The complete resolved plan, ready for API execution."""

    model_config = ConfigDict(extra="forbid")

    # Metadata
    template_name: str
    template_version: str
    instance_org: str
    instance_repo: str
    target: str
    project_name: str
    project_description: str

    # Resolved resources
    status_options: list[StatusOption]
    fields: list[ResolvedField]
    milestones: list[ResolvedMilestone]
    issues: list[ResolvedIssue]
    views: list[ViewDefinition]

    # Placeholder values used (for audit trail)
    placeholder_values: dict[str, str]

    # Skip/prune summary
    skipped_milestones: list[str]
    skipped_issues: list[str]

    # Warnings
    warnings: list[str]
