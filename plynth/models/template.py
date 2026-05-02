from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class TemplateMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    version: str
    source_doc: str | None = None


class PlaceholderSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    example: str
    required: bool = True


class StatusOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    color: Literal["GRAY", "BLUE", "YELLOW", "RED", "PURPLE", "GREEN"]


class FieldDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: Literal["single_select", "text", "number", "date", "iteration"]
    options: list[str] = []


class MilestoneDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str
    due_offset_weeks: int
    optional: bool = False


class IssueDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str
    title: str
    milestone_id: str
    fields: dict[str, str] = {}
    blocked_by: list[str] = []
    blocks: list[str] = []
    body: str = ""


class ViewSort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    direction: Literal["asc", "desc"]


class ViewFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    operator: str
    value: str


class ViewDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    layout: Literal["board", "table", "roadmap"]
    group_by: str | None = None
    slice_by: str | None = None
    sort: ViewSort | None = None
    filter: ViewFilter | None = None
    visible_fields: list[str] = []
    description: str = ""


class PruningRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_value: str
    keep_issues: list[str] = []
    remove_issues: list[str] = []


class PruningConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger_issue: str
    decision_field: str
    rules: list[PruningRule]


class TemplateDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    template: TemplateMetadata
    placeholders: dict[str, PlaceholderSpec] = {}
    status: list[StatusOption] = []
    fields: list[FieldDefinition] = []
    milestones: list[MilestoneDefinition] = []
    issues: list[IssueDefinition] = []
    views: list[ViewDefinition] = []
    pruning: PruningConfig | None = None

    @model_validator(mode="after")
    def _validate_references(self) -> TemplateDefinition:
        milestone_ids = {m.id for m in self.milestones}
        template_ids = {i.template_id for i in self.issues}
        field_ids = {f.id for f in self.fields}

        errors: list[str] = []

        for issue in self.issues:
            if issue.milestone_id not in milestone_ids:
                errors.append(
                    f"Issue {issue.template_id}: milestone_id "
                    f"'{issue.milestone_id}' not found in milestones"
                )

            for ref in issue.blocked_by:
                if ref not in template_ids:
                    errors.append(
                        f"Issue {issue.template_id}: blocked_by ref '{ref}' not found in issues"
                    )

            for ref in issue.blocks:
                if ref not in template_ids:
                    errors.append(
                        f"Issue {issue.template_id}: blocks ref '{ref}' not found in issues"
                    )

            for field_key in issue.fields:
                if field_key not in field_ids:
                    errors.append(
                        f"Issue {issue.template_id}: field key '{field_key}' not found in fields"
                    )

        if self.pruning:
            if self.pruning.trigger_issue not in template_ids:
                errors.append(
                    f"Pruning trigger_issue '{self.pruning.trigger_issue}' not found in issues"
                )
            for rule in self.pruning.rules:
                for ref in rule.keep_issues:
                    if ref not in template_ids:
                        errors.append(f"Pruning keep_issues ref '{ref}' not found in issues")
                for ref in rule.remove_issues:
                    if ref not in template_ids:
                        errors.append(f"Pruning remove_issues ref '{ref}' not found in issues")

        if errors:
            raise ValueError("Template reference validation failed:\n  " + "\n  ".join(errors))

        return self
