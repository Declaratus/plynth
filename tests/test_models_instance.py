from __future__ import annotations

import pytest
from pydantic import ValidationError

from plynth.models.instance import InstanceConfig


def _base_instance_dict() -> dict:
    return {
        "template": "t.yaml",
        "target": "https://ghes.example.com",
        "org": "example-org",
        "values": {"APP": "Acme"},
        "repo": {"name": "acme"},
        "project": {"name": "Acme"},
    }


def test_target_trailing_slash_stripped() -> None:
    data = _base_instance_dict()
    data["target"] = "https://ghes.example.com/"
    cfg = InstanceConfig.model_validate(data)
    assert cfg.target == "https://ghes.example.com"


def test_target_multi_trailing_slash_stripped() -> None:
    data = _base_instance_dict()
    data["target"] = "https://ghes.example.com///"
    cfg = InstanceConfig.model_validate(data)
    assert cfg.target == "https://ghes.example.com"


def test_target_github_com_accepted() -> None:
    data = _base_instance_dict()
    data["target"] = "github.com"
    cfg = InstanceConfig.model_validate(data)
    assert cfg.target == "github.com"


def test_target_empty_accepted_as_github_com_default() -> None:
    data = _base_instance_dict()
    data["target"] = ""
    cfg = InstanceConfig.model_validate(data)
    assert cfg.target == ""


def test_target_https_api_github_com_accepted() -> None:
    data = _base_instance_dict()
    data["target"] = "https://api.github.com"
    cfg = InstanceConfig.model_validate(data)
    assert cfg.target == "https://api.github.com"


def test_target_https_github_com_rejected_with_fix_it() -> None:
    """https://github.com is the web host, not the API. Don't auto-correct it."""
    data = _base_instance_dict()
    data["target"] = "https://github.com"
    with pytest.raises(ValidationError, match="api.github.com"):
        InstanceConfig.model_validate(data)


def test_target_http_rejected() -> None:
    data = _base_instance_dict()
    data["target"] = "http://ghes.example.com"
    with pytest.raises(ValidationError, match="only https"):
        InstanceConfig.model_validate(data)


def test_target_bare_hostname_rejected() -> None:
    data = _base_instance_dict()
    data["target"] = "ghes.example.com"
    with pytest.raises(ValidationError, match="https"):
        InstanceConfig.model_validate(data)


def test_legacy_ghes_url_key_rejected_with_migration_hint() -> None:
    """A v0.2.0 instance file using `ghes_url:` should fail loudly with a hint."""
    data = _base_instance_dict()
    data.pop("target")
    data["ghes_url"] = "https://ghes.example.com"
    with pytest.raises(ValidationError) as exc_info:
        InstanceConfig.model_validate(data)
    msg = str(exc_info.value)
    assert "target" in msg
    assert "0.3.0" in msg


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


def test_project_name_over_limit_rejected() -> None:
    data = _base_instance_dict()
    data["project"]["name"] = "x" * 257
    with pytest.raises(ValidationError):
        InstanceConfig.model_validate(data)


def test_project_description_over_limit_rejected() -> None:
    data = _base_instance_dict()
    data["project"]["description"] = "x" * 8_193
    with pytest.raises(ValidationError):
        InstanceConfig.model_validate(data)
