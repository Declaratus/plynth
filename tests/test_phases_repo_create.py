"""Tests for Phase 1's `repo.create: true` path (issue #13).

Covers the three acceptance cases:
- create=true + missing repo → create, then proceed
- create=true + existing repo → no-op (idempotent), proceed
- create=false (default) + missing repo → friendly NotFoundError, no create call
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from plynth.engine.phases import PhaseOrchestrator
from plynth.errors import NotFoundError
from plynth.models.state import StateFile


def _make_orchestrator(
    mocker: MockerFixture,
    state_path: Path,
    *,
    repo_create: bool,
) -> PhaseOrchestrator:
    plan = mocker.MagicMock()
    plan.instance_org = "example-org"
    plan.instance_repo = "acme"
    plan.instance_repo_create = repo_create
    state = StateFile(target="https://ghes.example.com", org="example-org")
    return PhaseOrchestrator(
        plan=plan,
        gql=mocker.MagicMock(),
        rest=mocker.MagicMock(),
        state=state,
        state_path=state_path,
        logger=logging.getLogger("plynth.test"),
    )


def test_repo_create_true_missing_repo_creates_then_resolves(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    orch = _make_orchestrator(mocker, tmp_path / "state.yaml", repo_create=True)
    # First lookup misses, second lookup (post-create) hits.
    orch.gql.get_repo_id.side_effect = [
        NotFoundError("Could not resolve to a Repository"),
        "R_after_create",
    ]

    repo_id = orch._resolve_repo_id()

    assert repo_id == "R_after_create"
    orch.rest.create_repo.assert_called_once_with("example-org", "acme")
    assert orch.gql.get_repo_id.call_count == 2


def test_repo_create_true_existing_repo_is_noop(mocker: MockerFixture, tmp_path: Path) -> None:
    orch = _make_orchestrator(mocker, tmp_path / "state.yaml", repo_create=True)
    orch.gql.get_repo_id.return_value = "R_existing"

    repo_id = orch._resolve_repo_id()

    assert repo_id == "R_existing"
    orch.rest.create_repo.assert_not_called()
    assert orch.gql.get_repo_id.call_count == 1


def test_repo_create_false_missing_repo_propagates_not_found(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    orch = _make_orchestrator(mocker, tmp_path / "state.yaml", repo_create=False)
    orch.gql.get_repo_id.side_effect = NotFoundError("Could not resolve to a Repository")

    with pytest.raises(NotFoundError, match="Could not resolve to a Repository"):
        orch._resolve_repo_id()

    orch.rest.create_repo.assert_not_called()
