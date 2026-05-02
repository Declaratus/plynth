from __future__ import annotations

import pytest

from plynth.engine.planner import format_dry_run, plan, resolve_placeholders
from plynth.models.instance import InstanceConfig
from plynth.models.template import TemplateDefinition


def test_resolve_placeholders_basic() -> None:
    result = resolve_placeholders("Hello {APP}!", {"APP": "Acme"})
    assert result == "Hello Acme!"


def test_resolve_placeholders_preserves_crossrefs() -> None:
    body = "See {PREFIX}-001 and {PREFIX}-002. App is {APP}."
    result = resolve_placeholders(body, {"PREFIX": "ACME", "APP": "Acme"}, preserve_crossrefs=True)
    assert "{PREFIX}-001" in result
    assert "{PREFIX}-002" in result
    assert "App is Acme." in result


def test_resolve_placeholders_resolves_when_not_preserving() -> None:
    body = "See {PREFIX}-001."
    result = resolve_placeholders(body, {"PREFIX": "ACME"})
    assert result == "See ACME-001."


def test_plan_basic(minimal_template: TemplateDefinition, minimal_instance: InstanceConfig) -> None:
    ep = plan(minimal_template, minimal_instance)
    assert ep.template_name == "Minimal Test Template"
    assert ep.instance_org == "example-org"
    assert ep.project_name == "Acme Bootstrap"
    assert len(ep.milestones) == 2
    assert len(ep.issues) == 3
    assert ep.warnings == []


def test_plan_resolves_placeholders_in_titles(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    ep = plan(minimal_template, minimal_instance)
    titles = [i.title for i in ep.issues]
    assert "Bootstrap Acme" in titles
    assert all("{APP}" not in t for t in titles)
    milestone_titles = [m.title for m in ep.milestones]
    assert "Acme Foundation" in milestone_titles


def test_plan_resolves_team_placeholder_in_field_options(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    ep = plan(minimal_template, minimal_instance)
    priority = next(f for f in ep.fields if f.id == "priority")
    assert "Platform" in priority.options
    assert "{TEAM}" not in priority.options


def test_plan_preserves_crossrefs_in_bodies(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    ep = plan(minimal_template, minimal_instance)
    bodies = [i.body for i in ep.issues]
    assert any("{PREFIX}-001" in b for b in bodies)


def test_plan_milestone_due_date_math(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    ep = plan(minimal_template, minimal_instance)
    m1 = next(m for m in ep.milestones if m.id == "M1")
    m2 = next(m for m in ep.milestones if m.id == "M2")
    # start_date 2026-05-01 + 2 weeks = 2026-05-15
    assert m1.due_date == "2026-05-15"
    # + 4 weeks = 2026-05-29
    assert m2.due_date == "2026-05-29"


def test_plan_skip_milestone_cascades(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    minimal_instance.skip_milestones = ["M2"]
    ep = plan(minimal_template, minimal_instance)
    assert [m.id for m in ep.milestones] == ["M1"]
    # ACME-003 lives on M2 → should be skipped
    issue_ids = [i.template_id for i in ep.issues]
    assert "{PREFIX}-003" not in issue_ids
    assert "{PREFIX}-001" in issue_ids
    assert "{PREFIX}-002" in issue_ids


def test_plan_skip_milestone_trims_dependencies(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    minimal_instance.skip_milestones = ["M1"]
    ep = plan(minimal_template, minimal_instance)
    # All deps should be trimmed since M1 is gone (ACME-001, ACME-002 removed)
    only_issue = ep.issues[0]
    assert only_issue.template_id == "{PREFIX}-003"
    assert only_issue.blocked_by == []
    # The skipped ref should be recorded
    assert "{PREFIX}-002" in only_issue.skipped_blocked_by
    assert ep.warnings, "Expected warnings about trimmed deps"


def test_plan_missing_required_placeholder_raises(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    minimal_instance.values = {"PREFIX": "ACME"}  # APP missing
    with pytest.raises(ValueError, match="Missing required placeholder"):
        plan(minimal_template, minimal_instance)


def test_format_dry_run_shape(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    ep = plan(minimal_template, minimal_instance)
    output = format_dry_run(ep)
    assert "plynth Execution Plan" in output
    assert "Acme Bootstrap" in output
    assert "Milestones" in output
    assert "Issues" in output
    assert "Fields" in output
