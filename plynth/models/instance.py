from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator


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
    ghes_url: str
    org: str
    values: dict[str, str]
    repo: RepoConfig
    project: ProjectConfig
    skip_milestones: list[str] = []
    skip_issues: list[str] = []
    field_overrides: dict[str, dict[str, str]] = {}
    start_date: str | None = None
    pruning_decision: dict[str, str] | None = None

    @field_validator("ghes_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("start_date")
    @classmethod
    def _validate_date_format(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise ValueError(
                    f"start_date must be YYYY-MM-DD format, got '{v}'"
                )
        return v
