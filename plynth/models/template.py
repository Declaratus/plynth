from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# GitHub's Projects V2 single-select option color set. Sourced from the GHES
# 3.19 GraphQL schema (ProjectV2SingleSelectFieldOptionColor enum). Pydantic
# rejects out-of-set colors at template parse time, so the engine never sees
# an invalid value. Add an entry here when a future GHES version adds one.
OptionColor = Literal["GRAY", "BLUE", "YELLOW", "RED", "PURPLE", "GREEN", "ORANGE", "PINK"]


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


class FieldOption(BaseModel):
    """Rich form of a single-select field option.

    Templates may declare options as plain strings (legacy) or as objects
    with color/description/default/aliases/deprecated. A field_validator on
    FieldDefinition.options normalizes strings to FieldOption(value=...) so
    the engine sees one shape post-parse. The same shape powers the
    template-level ``status:`` block (the project's built-in Status field).
    """

    model_config = ConfigDict(extra="forbid")

    value: Annotated[str, Field(max_length=100)]
    color: OptionColor | None = None
    description: str = Field(default="", max_length=2_000)
    default: bool = False
    aliases: list[Annotated[str, Field(max_length=100)]] = []
    deprecated: bool = False


def _normalize_string_options(v: Any) -> Any:
    """Coerce a list that may mix strings and dicts into a list of dicts.

    Used by both ``FieldDefinition.options`` and ``TemplateDefinition.status``
    so legacy string-only YAML keeps parsing while richer objects roundtrip.
    """
    if not isinstance(v, list):
        return v
    return [{"value": opt} if isinstance(opt, str) else opt for opt in v]


def _check_at_most_one_default(options: list[FieldOption], context: str) -> None:
    defaults = [opt.value for opt in options if opt.default]
    if len(defaults) > 1:
        raise ValueError(
            f"{context}: at most one option may have default: true "
            f"(found {len(defaults)}: {defaults})"
        )


class FieldDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: Literal["single_select", "text", "number", "date", "iteration"]
    options: list[FieldOption] = []
    allow_unknown_values: bool = False

    @field_validator("options", mode="before")
    @classmethod
    def _normalize_options(cls, v: Any) -> Any:
        return _normalize_string_options(v)

    @model_validator(mode="after")
    def _at_most_one_default(self) -> FieldDefinition:
        _check_at_most_one_default(self.options, f"Field '{self.id}'")
        return self


class MilestoneDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str = Field(max_length=256)
    description: str = Field(max_length=65_536)
    due_offset_weeks: int
    optional: bool = False


class IssueDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str
    title: str = Field(max_length=256)
    milestone_id: str
    fields: dict[str, str] = {}
    blocked_by: list[str] = []
    blocks: list[str] = []
    body: str = Field(default="", max_length=65_536)


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


class TemplateDefaults(BaseModel):
    """Template-level defaults applied to every issue unless overridden.

    Precedence (lowest to highest): engine fallback, template defaults,
    per-issue values, instance field_overrides. Labels are intentionally
    deferred until the labels-and-issue-types feature lands.
    """

    model_config = ConfigDict(extra="forbid")

    fields: dict[str, str] = {}


class ReconciliationConfig(BaseModel):
    """Reserved namespace for the reconciliation/verify lifecycle.

    Today only ``mode: none`` is honored. ``report_only`` parses but is
    treated identically to ``none`` until the verify subcommand lands.
    The namespace is reserved now because every model uses extra="forbid",
    so adding fields later breaks anyone who put a placeholder block in.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["none", "report_only"] = "none"
    verify_after_apply: bool = False


class TemplateDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # See docs/plynth-design-spec.md#schema-versioning for the cadence.
    # A template that omits `schema_version` is parsed as "1.0" (pre-M1).
    # M1+ features (`defaults`, rich `FieldOption`, `reconciliation`) should
    # declare `schema_version: "1.1"`; today the engine accepts them either
    # way, but the table is the source of truth for what each version adds.
    schema_version: str = "1.0"
    template: TemplateMetadata
    placeholders: dict[str, PlaceholderSpec] = {}
    status: list[FieldOption] = []
    fields: list[FieldDefinition] = []
    milestones: list[MilestoneDefinition] = []
    issues: list[IssueDefinition] = []
    views: list[ViewDefinition] = []
    pruning: PruningConfig | None = None
    defaults: TemplateDefaults = Field(default_factory=TemplateDefaults)
    reconciliation: ReconciliationConfig = Field(default_factory=ReconciliationConfig)

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, v: Any) -> Any:
        return _normalize_string_options(v)

    @model_validator(mode="after")
    def _status_at_most_one_default(self) -> TemplateDefinition:
        _check_at_most_one_default(self.status, "status")
        return self

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

        for field_key in self.defaults.fields:
            if field_key not in field_ids:
                errors.append(f"defaults.fields: key '{field_key}' not found in fields")

        if errors:
            raise ValueError("Template reference validation failed:\n  " + "\n  ".join(errors))

        return self
