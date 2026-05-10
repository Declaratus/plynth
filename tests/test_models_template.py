from __future__ import annotations

import pytest
from pydantic import ValidationError

from plynth.models.template import TemplateDefinition


def _base_template_dict() -> dict:
    return {
        "schema_version": "1.0",
        "template": {"name": "T", "description": "d", "version": "0.0.1"},
        "placeholders": {},
        "status": [{"value": "Todo", "color": "GRAY"}],
        "fields": [
            {"id": "priority", "name": "Priority", "type": "single_select", "options": ["P1"]}
        ],
        "milestones": [{"id": "M1", "title": "First", "description": "", "due_offset_weeks": 1}],
        "issues": [
            {
                "template_id": "T-001",
                "title": "i1",
                "milestone_id": "M1",
                "fields": {"priority": "P1"},
            }
        ],
    }


def test_minimal_template_loads(minimal_template: TemplateDefinition) -> None:
    assert minimal_template.template.name == "Minimal Test Template"
    assert len(minimal_template.milestones) == 2
    assert len(minimal_template.issues) == 3


def test_unknown_milestone_id_rejected() -> None:
    data = _base_template_dict()
    data["issues"][0]["milestone_id"] = "DOES_NOT_EXIST"
    with pytest.raises(ValidationError, match="milestone_id 'DOES_NOT_EXIST' not found"):
        TemplateDefinition.model_validate(data)


def test_unknown_blocked_by_rejected() -> None:
    data = _base_template_dict()
    data["issues"][0]["blocked_by"] = ["T-999"]
    with pytest.raises(ValidationError, match="blocked_by ref 'T-999' not found"):
        TemplateDefinition.model_validate(data)


def test_unknown_field_key_rejected() -> None:
    data = _base_template_dict()
    data["issues"][0]["fields"] = {"bogus_field": "X"}
    with pytest.raises(ValidationError, match="field key 'bogus_field' not found"):
        TemplateDefinition.model_validate(data)


def test_extra_keys_rejected() -> None:
    data = _base_template_dict()
    data["unknown_key"] = "oops"
    with pytest.raises(ValidationError):
        TemplateDefinition.model_validate(data)


def test_invalid_status_color_rejected() -> None:
    data = _base_template_dict()
    data["status"][0]["color"] = "TEAL"
    with pytest.raises(ValidationError):
        TemplateDefinition.model_validate(data)


def test_status_accepts_full_option_color_set() -> None:
    """status: now uses FieldOption, so ORANGE and PINK are valid (not just
    the six-color subset the dropped StatusOption model allowed)."""
    data = _base_template_dict()
    data["status"] = [
        {"value": "Triaged", "color": "ORANGE"},
        {"value": "Done", "color": "PINK"},
    ]
    t = TemplateDefinition.model_validate(data)
    assert [o.color for o in t.status] == ["ORANGE", "PINK"]


def test_pruning_unknown_trigger_rejected() -> None:
    data = _base_template_dict()
    data["pruning"] = {
        "trigger_issue": "T-NOPE",
        "decision_field": "priority",
        "rules": [],
    }
    with pytest.raises(ValidationError, match="trigger_issue 'T-NOPE' not found"):
        TemplateDefinition.model_validate(data)


def test_issue_title_over_limit_rejected() -> None:
    data = _base_template_dict()
    data["issues"][0]["title"] = "x" * 257
    with pytest.raises(ValidationError):
        TemplateDefinition.model_validate(data)


def test_issue_body_over_limit_rejected() -> None:
    data = _base_template_dict()
    data["issues"][0]["body"] = "x" * 65_537
    with pytest.raises(ValidationError):
        TemplateDefinition.model_validate(data)


def test_milestone_title_over_limit_rejected() -> None:
    data = _base_template_dict()
    data["milestones"][0]["title"] = "x" * 257
    with pytest.raises(ValidationError):
        TemplateDefinition.model_validate(data)


def test_milestone_description_over_limit_rejected() -> None:
    data = _base_template_dict()
    data["milestones"][0]["description"] = "x" * 65_537
    with pytest.raises(ValidationError):
        TemplateDefinition.model_validate(data)


def test_field_option_name_over_limit_rejected() -> None:
    data = _base_template_dict()
    data["fields"][0]["options"] = ["x" * 101]
    with pytest.raises(ValidationError):
        TemplateDefinition.model_validate(data)


# ── M1-A: rich field option objects ────────────────────────────────


def test_field_option_legacy_string_form_normalizes() -> None:
    data = _base_template_dict()
    data["fields"][0]["options"] = ["P1", "P2"]
    t = TemplateDefinition.model_validate(data)
    opts = t.fields[0].options
    assert [o.value for o in opts] == ["P1", "P2"]
    assert all(o.color is None for o in opts)
    assert all(o.description == "" for o in opts)
    assert all(o.default is False for o in opts)


def test_field_option_rich_form_roundtrips() -> None:
    data = _base_template_dict()
    data["fields"][0]["options"] = [
        "P1",
        {
            "value": "P2",
            "color": "RED",
            "description": "Critical",
            "default": True,
            "aliases": ["urgent"],
            "deprecated": False,
        },
    ]
    t = TemplateDefinition.model_validate(data)
    opts = t.fields[0].options
    assert opts[0].value == "P1" and opts[0].color is None
    assert opts[1].value == "P2"
    assert opts[1].color == "RED"
    assert opts[1].description == "Critical"
    assert opts[1].default is True
    assert opts[1].aliases == ["urgent"]


def test_field_option_invalid_color_rejected() -> None:
    data = _base_template_dict()
    data["fields"][0]["options"] = [{"value": "P1", "color": "TEAL"}]
    with pytest.raises(ValidationError):
        TemplateDefinition.model_validate(data)


def test_field_option_two_defaults_rejected() -> None:
    data = _base_template_dict()
    data["fields"][0]["options"] = [
        {"value": "P1", "default": True},
        {"value": "P2", "default": True},
    ]
    with pytest.raises(ValidationError, match="at most one option may have default"):
        TemplateDefinition.model_validate(data)


def test_field_allow_unknown_values_defaults_false() -> None:
    data = _base_template_dict()
    t = TemplateDefinition.model_validate(data)
    assert t.fields[0].allow_unknown_values is False


# ── M1-B: template-level defaults ──────────────────────────────────


def test_template_defaults_default_empty() -> None:
    t = TemplateDefinition.model_validate(_base_template_dict())
    assert t.defaults.fields == {}


def test_template_defaults_parses() -> None:
    data = _base_template_dict()
    data["defaults"] = {"fields": {"priority": "P1"}}
    t = TemplateDefinition.model_validate(data)
    assert t.defaults.fields == {"priority": "P1"}


def test_template_defaults_unknown_field_key_rejected() -> None:
    data = _base_template_dict()
    data["defaults"] = {"fields": {"nope": "x"}}
    with pytest.raises(ValidationError, match="defaults.fields: key 'nope' not found"):
        TemplateDefinition.model_validate(data)


# ── #14: configurable Status field ─────────────────────────────────


def test_status_legacy_string_form_normalizes() -> None:
    data = _base_template_dict()
    data["status"] = ["Triaged", "Done"]
    t = TemplateDefinition.model_validate(data)
    assert [o.value for o in t.status] == ["Triaged", "Done"]
    assert all(o.color is None for o in t.status)
    assert all(o.default is False for o in t.status)


def test_status_rich_form_roundtrips() -> None:
    data = _base_template_dict()
    data["status"] = [
        {"value": "Triaged", "color": "GRAY", "default": True},
        {"value": "Spec'd", "color": "BLUE", "description": "Acceptance written"},
        "Done",  # mixing legacy strings allowed
    ]
    t = TemplateDefinition.model_validate(data)
    assert [o.value for o in t.status] == ["Triaged", "Spec'd", "Done"]
    assert t.status[0].default is True
    assert t.status[1].description == "Acceptance written"
    assert t.status[2].color is None


def test_status_two_defaults_rejected() -> None:
    data = _base_template_dict()
    data["status"] = [
        {"value": "Triaged", "default": True},
        {"value": "Done", "default": True},
    ]
    with pytest.raises(ValidationError, match="at most one option may have default"):
        TemplateDefinition.model_validate(data)


def test_status_empty_list_is_valid() -> None:
    """No status block (or empty) means 'keep GitHub defaults' — supported."""
    data = _base_template_dict()
    data["status"] = []
    t = TemplateDefinition.model_validate(data)
    assert t.status == []


# ── M1-G: reconciliation namespace stub ────────────────────────────


def test_reconciliation_default_none() -> None:
    t = TemplateDefinition.model_validate(_base_template_dict())
    assert t.reconciliation.mode == "none"
    assert t.reconciliation.verify_after_apply is False


def test_reconciliation_report_only_parses() -> None:
    data = _base_template_dict()
    data["reconciliation"] = {"mode": "report_only", "verify_after_apply": True}
    t = TemplateDefinition.model_validate(data)
    assert t.reconciliation.mode == "report_only"
    assert t.reconciliation.verify_after_apply is True


def test_reconciliation_invalid_mode_rejected() -> None:
    data = _base_template_dict()
    data["reconciliation"] = {"mode": "apply"}
    with pytest.raises(ValidationError):
        TemplateDefinition.model_validate(data)
