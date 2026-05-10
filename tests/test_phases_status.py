"""Phase-level tests for the configurable Status field (#14).

Covers the three behaviors that don't need the full e2e dispatcher:

* Status overwrite is gated on the introspection probe — a 3.18 instance
  must fail before any project is created (no orphan projects).
* An empty ``plan.status_options`` skips both the probe and the mutation
  and keeps the pre-#14 ``Backlog`` default.
* Phase 4b reads the configured default rather than the old hard-coded
  ``Backlog`` string.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from plynth.engine.phases import PhaseOrchestrator
from plynth.errors import PlynthError
from plynth.models.plan import (
    ExecutionPlan,
    ResolvedField,
    ResolvedFieldOption,
    ResolvedIssue,
    ResolvedMilestone,
)
from plynth.models.state import StateFile


def _make_plan(
    *,
    status_options: list[ResolvedFieldOption] | None = None,
    issues: list[ResolvedIssue] | None = None,
) -> ExecutionPlan:
    return ExecutionPlan(
        template_name="t",
        template_version="0.0.1",
        instance_org="example-org",
        instance_repo="acme",
        target="https://ghes.example.com",
        project_name="Acme",
        project_description="",
        status_options=status_options or [],
        fields=[ResolvedField(id="priority", name="Priority", type="single_select", options=[])],
        milestones=[ResolvedMilestone(id="M1", title="M1", description="", due_date=None)],
        issues=issues
        or [
            ResolvedIssue(
                template_id="001",
                title="i1",
                body="b",
                milestone_id="M1",
                fields={},
                blocked_by=[],
                blocks=[],
                skipped_blocked_by=[],
                skipped_blocks=[],
            )
        ],
        views=[],
        placeholder_values={},
        skipped_milestones=[],
        skipped_issues=[],
        warnings=[],
    )


def _make_orchestrator(
    mocker: MockerFixture,
    plan: ExecutionPlan,
    state_path: Path,
) -> tuple[PhaseOrchestrator, StateFile]:
    state = StateFile(target=plan.target, org=plan.instance_org)
    gql = mocker.MagicMock()
    gql.base.display_target = "ghes.example.com"
    rest = mocker.MagicMock()
    orch = PhaseOrchestrator(
        plan=plan,
        gql=gql,
        rest=rest,
        state=state,
        state_path=state_path,
        logger=logging.getLogger("plynth.test"),
    )
    return orch, state


def test_phase_1_probe_runs_before_any_side_effects_when_unsupported(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """A 3.18 instance must fail before _resolve_repo_id() runs — otherwise
    `repo.create: true` would create a repo we'd immediately abandon when
    the probe failed (orphan-repo bug Copilot caught on PR #57)."""
    plan = _make_plan(
        status_options=[
            ResolvedFieldOption(value="Todo", color="GRAY", default=True),
        ]
    )
    orch, _ = _make_orchestrator(mocker, plan, tmp_path / "state.yaml")
    orch.gql.supports_status_overwrite.return_value = False
    orch.gql.get_org_id.return_value = "O_1"
    orch.gql.get_repo_id.return_value = "R_1"

    with pytest.raises(PlynthError, match="GHES 3.19"):
        orch.phase_1_create_project_and_fields()

    # Probe gates on schema only; nothing touching the org/repo/project
    # surface should have run.
    orch.gql.get_org_id.assert_not_called()
    orch.gql.get_repo_id.assert_not_called()
    orch.rest.create_repo.assert_not_called()
    orch.gql.create_project.assert_not_called()
    orch.gql.create_field.assert_not_called()
    orch.gql.update_field_options.assert_not_called()


def test_phase_1_skips_probe_and_mutation_when_status_unconfigured(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """No status block means no probe and no mutation — backward-compatible
    with templates written before #14."""
    plan = _make_plan(status_options=[])
    orch, state = _make_orchestrator(mocker, plan, tmp_path / "state.yaml")
    orch.gql.get_org_id.return_value = "O_1"
    orch.gql.get_repo_id.return_value = "R_1"
    orch.gql.create_project.return_value = {
        "id": "PVT_1",
        "url": "https://x",
        "number": 1,
    }
    orch.gql.get_project_fields.return_value = [
        {
            "id": "PVTSSF_status",
            "name": "Status",
            "options": [{"id": "opt_backlog", "name": "Backlog"}],
        },
    ]

    orch.phase_1_create_project_and_fields()

    orch.gql.supports_status_overwrite.assert_not_called()
    orch.gql.update_field_options.assert_not_called()
    assert state.fields["_status"].options == {"Backlog": "opt_backlog"}


def test_phase_1_overwrites_status_options_when_configured(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    plan = _make_plan(
        status_options=[
            ResolvedFieldOption(value="Triaged", color="GRAY", default=True),
            ResolvedFieldOption(value="Done", color="GREEN"),
        ]
    )
    orch, state = _make_orchestrator(mocker, plan, tmp_path / "state.yaml")
    orch.gql.supports_status_overwrite.return_value = True
    orch.gql.get_org_id.return_value = "O_1"
    orch.gql.get_repo_id.return_value = "R_1"
    orch.gql.create_project.return_value = {
        "id": "PVT_1",
        "url": "https://x",
        "number": 1,
    }
    orch.gql.get_project_fields.return_value = [
        {
            "id": "PVTSSF_status",
            "name": "Status",
            "options": [{"id": "opt_backlog", "name": "Backlog"}],
        },
    ]
    orch.gql.update_field_options.return_value = [
        {"id": "opt_triaged", "name": "Triaged", "color": "GRAY"},
        {"id": "opt_done", "name": "Done", "color": "GREEN"},
    ]

    orch.phase_1_create_project_and_fields()

    orch.gql.update_field_options.assert_called_once()
    field_id, sent_options = orch.gql.update_field_options.call_args.args
    assert field_id == "PVTSSF_status"
    assert [o["name"] for o in sent_options] == ["Triaged", "Done"]
    assert state.fields["_status"].options == {
        "Triaged": "opt_triaged",
        "Done": "opt_done",
    }


def test_resolve_default_status_value_picks_explicit_default(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    plan = _make_plan(
        status_options=[
            ResolvedFieldOption(value="Triaged", color="GRAY"),
            ResolvedFieldOption(value="Done", color="GREEN", default=True),
        ]
    )
    orch, _ = _make_orchestrator(mocker, plan, tmp_path / "state.yaml")
    assert orch._resolve_default_status_value() == "Done"


def test_resolve_default_status_value_falls_back_to_first_option(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    plan = _make_plan(
        status_options=[
            ResolvedFieldOption(value="Triaged", color="GRAY"),
            ResolvedFieldOption(value="Done", color="GREEN"),
        ]
    )
    orch, _ = _make_orchestrator(mocker, plan, tmp_path / "state.yaml")
    assert orch._resolve_default_status_value() == "Triaged"


def test_resolve_default_status_value_keeps_backlog_when_unconfigured(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    plan = _make_plan(status_options=[])
    orch, _ = _make_orchestrator(mocker, plan, tmp_path / "state.yaml")
    assert orch._resolve_default_status_value() == "Backlog"
