from __future__ import annotations

import pytest
from pydantic import ValidationError

from plynth.models.instance import InstanceConfig


def _base_instance_dict() -> dict:
    return {
        "template": "t.yaml",
        "ghes_url": "https://ghes.example.com",
        "org": "example-org",
        "values": {"APP": "Acme"},
        "repo": {"name": "acme"},
        "project": {"name": "Acme"},
    }


def test_ghes_url_trailing_slash_stripped() -> None:
    data = _base_instance_dict()
    data["ghes_url"] = "https://ghes.example.com/"
    cfg = InstanceConfig.model_validate(data)
    assert cfg.ghes_url == "https://ghes.example.com"


def test_ghes_url_multi_trailing_slash_stripped() -> None:
    data = _base_instance_dict()
    data["ghes_url"] = "https://ghes.example.com///"
    cfg = InstanceConfig.model_validate(data)
    assert cfg.ghes_url == "https://ghes.example.com"


def test_start_date_valid_iso() -> None:
    data = _base_instance_dict()
    data["start_date"] = "2026-05-01"
    cfg = InstanceConfig.model_validate(data)
    assert cfg.start_date == "2026-05-01"


def test_start_date_none_allowed() -> None:
    cfg = InstanceConfig.model_validate(_base_instance_dict())
    assert cfg.start_date is None


def test_start_date_bad_format_rejected() -> None:
    data = _base_instance_dict()
    data["start_date"] = "05/01/2026"
    with pytest.raises(ValidationError, match="start_date must be YYYY-MM-DD"):
        InstanceConfig.model_validate(data)


def test_extra_keys_rejected() -> None:
    data = _base_instance_dict()
    data["bogus"] = "x"
    with pytest.raises(ValidationError):
        InstanceConfig.model_validate(data)


def test_defaults() -> None:
    cfg = InstanceConfig.model_validate(_base_instance_dict())
    assert cfg.skip_milestones == []
    assert cfg.skip_issues == []
    assert cfg.field_overrides == {}
    assert cfg.pruning_decision is None
    assert cfg.repo.create is False
