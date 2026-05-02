from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class RepoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    create: bool = False


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""


class InstanceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: str
    target: str
    org: str
    values: dict[str, str]
    repo: RepoConfig
    project: ProjectConfig
    skip_milestones: list[str] = []
    skip_issues: list[str] = []
    field_overrides: dict[str, dict[str, str]] = {}
    start_date: str | None = None
    pruning_decision: dict[str, str] | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_legacy_ghes_url(cls, data: Any) -> Any:
        """v0.2.0 used `ghes_url`. Reject it loudly so users update their config."""
        if isinstance(data, dict) and "ghes_url" in data:
            raise ValueError(
                "'ghes_url' was renamed to 'target' in v0.3.0. "
                "Use target: github.com (or https://api.github.com) for GitHub.com, "
                "or target: https://your-ghes.example.com for GHES. See CHANGELOG."
            )
        return data

    @field_validator("target")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("target")
    @classmethod
    def _validate_target(cls, v: str) -> str:
        from plynth.engine.api_base import derive_api_roots

        derive_api_roots(v)
        return v

    @field_validator("start_date")
    @classmethod
    def _validate_date_format(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                date.fromisoformat(v)
            except ValueError as e:
                raise ValueError(f"start_date must be YYYY-MM-DD format, got '{v}'") from e
        return v
