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
    values = [opt.value for opt in priority.options]
    assert "Platform" in values
    assert all("{TEAM}" not in v for v in values)


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
    # 003 lives on M2 → should be skipped
    issue_ids = [i.template_id for i in ep.issues]
    assert "003" not in issue_ids
    assert "001" in issue_ids
    assert "002" in issue_ids


def test_plan_skip_milestone_trims_dependencies(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    minimal_instance.skip_milestones = ["M1"]
    ep = plan(minimal_template, minimal_instance)
    # All deps should be trimmed since M1 is gone (001, 002 removed)
    only_issue = ep.issues[0]
    assert only_issue.template_id == "003"
    assert only_issue.blocked_by == []
    # The skipped ref should be recorded
    assert "002" in only_issue.skipped_blocked_by
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


# ── M1-A: rich field option resolution ────────────────────────────


def test_plan_rich_field_options_carry_color_and_description(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    minimal_template.fields[0].options[0].color = "RED"
    minimal_template.fields[0].options[0].description = "Critical"
    ep = plan(minimal_template, minimal_instance)
    priority = next(f for f in ep.fields if f.id == "priority")
    first = priority.options[0]
    assert first.color == "RED"
    assert first.description == "Critical"


def test_plan_known_color_unchanged(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    minimal_template.fields[0].options[0].color = "PURPLE"
    ep = plan(minimal_template, minimal_instance)
    priority = next(f for f in ep.fields if f.id == "priority")
    assert priority.options[0].color == "PURPLE"


def test_plan_omitted_color_materializes_as_gray(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    # Templates can leave color unset (None). The engine materializes None
    # as GRAY for the GraphQL mutation, which expects a concrete color.
    assert minimal_template.fields[0].options[0].color is None
    ep = plan(minimal_template, minimal_instance)
    priority = next(f for f in ep.fields if f.id == "priority")
    assert priority.options[0].color == "GRAY"


# ── M1-B: template defaults precedence ────────────────────────────


def test_plan_template_defaults_applied_when_issue_omits(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    minimal_template.defaults.fields = {"priority": "P2"}
    # Strip the per-issue priority on the first issue so the default kicks in.
    minimal_template.issues[0].fields = {}
    ep = plan(minimal_template, minimal_instance)
    first = next(i for i in ep.issues if i.template_id == minimal_template.issues[0].template_id)
    assert first.fields.get("priority") == "P2"


def test_plan_per_issue_field_wins_over_template_default(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    minimal_template.defaults.fields = {"priority": "P2"}
    minimal_template.issues[0].fields = {"priority": "P1"}
    ep = plan(minimal_template, minimal_instance)
    first = next(i for i in ep.issues if i.template_id == minimal_template.issues[0].template_id)
    assert first.fields.get("priority") == "P1"


def test_plan_instance_override_wins_over_per_issue_and_defaults(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    minimal_template.defaults.fields = {"priority": "P2"}
    minimal_template.issues[0].fields = {"priority": "P1"}
    tid = minimal_template.issues[0].template_id
    minimal_instance.field_overrides = {tid: {"priority": "Platform"}}
    ep = plan(minimal_template, minimal_instance)
    first = next(i for i in ep.issues if i.template_id == tid)
    assert first.fields.get("priority") == "Platform"


# ── M1-A: allow_unknown_values guard at plan time ──────────────────


def test_plan_unknown_field_value_rejected_by_default(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    # priority field defaults to allow_unknown_values=False; "Bogus" isn't
    # in the declared option set, so plan-time validation should fail.
    minimal_template.issues[0].fields = {"priority": "Bogus"}
    with pytest.raises(ValueError, match="not a declared option"):
        plan(minimal_template, minimal_instance)


def test_plan_unknown_field_value_allowed_when_allow_unknown_values_true(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    priority = next(f for f in minimal_template.fields if f.id == "priority")
    priority.allow_unknown_values = True
    minimal_template.issues[0].fields = {"priority": "Bogus"}
    ep = plan(minimal_template, minimal_instance)
    first = next(i for i in ep.issues if i.template_id == minimal_template.issues[0].template_id)
    assert first.fields["priority"] == "Bogus"


def test_plan_unknown_value_via_template_default_rejected(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    minimal_template.defaults.fields = {"priority": "Nope"}
    minimal_template.issues[0].fields = {}
    with pytest.raises(ValueError, match="not a declared option"):
        plan(minimal_template, minimal_instance)


def test_plan_unknown_value_via_instance_override_rejected(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    tid = minimal_template.issues[0].template_id
    minimal_instance.field_overrides = {tid: {"priority": "BadOverride"}}
    with pytest.raises(ValueError, match="not a declared option"):
        plan(minimal_template, minimal_instance)
