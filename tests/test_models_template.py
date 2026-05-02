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
    data["status"][0]["color"] = "ORANGE"
    with pytest.raises(ValidationError):
        TemplateDefinition.model_validate(data)


def test_pruning_unknown_trigger_rejected() -> None:
    data = _base_template_dict()
    data["pruning"] = {
        "trigger_issue": "T-NOPE",
        "decision_field": "priority",
        "rules": [],
    }
    with pytest.raises(ValidationError, match="trigger_issue 'T-NOPE' not found"):
        TemplateDefinition.model_validate(data)
