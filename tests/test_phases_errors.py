"""Tests for PhaseOrchestrator.execute() exception handling (item 1.7).

The orchestrator distinguishes user-facing PlynthError subclasses from
unexpected internal exceptions: both still write a state checkpoint
(so resume continues to work), but the recorded marker and log shape
differ so an operator inspecting the state file can tell which kind
of failure happened.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml
from pytest_mock import MockerFixture

from plynth.engine.phases import PhaseOrchestrator
from plynth.errors import AuthError, PlynthError
from plynth.models.state import PHASE_1_PROJECT_AND_FIELDS, StateFile


def _make_orchestrator(
    mocker: MockerFixture, state_path: Path
) -> tuple[PhaseOrchestrator, StateFile]:
    state = StateFile(target="https://ghes.example.com", org="example-org")
    orch = PhaseOrchestrator(
        plan=mocker.MagicMock(),
        gql=mocker.MagicMock(),
        rest=mocker.MagicMock(),
        state=state,
        state_path=state_path,
        logger=logging.getLogger("plynth.test"),
    )
    return orch, state


def test_plynth_error_is_recorded_with_clean_message_and_propagated(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    orch, state = _make_orchestrator(mocker, tmp_path / "state.yaml")
    mocker.patch.object(
        orch,
        "phase_1_create_project_and_fields",
        side_effect=AuthError("Token rejected (HTTP 401)"),
    )

    with pytest.raises(AuthError, match="Token rejected"):
        orch.execute()

    status = state.phases[PHASE_1_PROJECT_AND_FIELDS]
    assert status.completed is False
    # PlynthError messages are already user-friendly; no class prefix added.
    assert status.error == "Token rejected (HTTP 401)"


def test_unhandled_exception_is_recorded_with_class_prefix_and_propagated(
    mocker: MockerFixture, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    orch, state = _make_orchestrator(mocker, tmp_path / "state.yaml")
    mocker.patch.object(
        orch,
        "phase_1_create_project_and_fields",
        side_effect=RuntimeError("library blew up"),
    )

    with (
        caplog.at_level(logging.ERROR, logger="plynth.test"),
        pytest.raises(RuntimeError, match="library blew up"),
    ):
        orch.execute()

    status = state.phases[PHASE_1_PROJECT_AND_FIELDS]
    assert status.completed is False
    # Class name prefix lets an operator distinguish internal failures.
    assert status.error == "RuntimeError: library blew up"
    # log.exception was used for the unhandled path, so traceback is captured.
    matching = [r for r in caplog.records if "Unhandled error" in r.message]
    assert matching, "expected an 'Unhandled error' log record"
    assert matching[0].exc_info is not None


def test_state_checkpoint_is_persisted_before_exception_propagates(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Resume invariant: the failed phase's marker must be on disk before
    the exception leaves execute(), or a restart will silently re-run it
    without operator visibility into the prior failure."""
    state_path = tmp_path / "state.yaml"
    orch, _ = _make_orchestrator(mocker, state_path)
    mocker.patch.object(
        orch,
        "phase_1_create_project_and_fields",
        side_effect=PlynthError("network fell over"),
    )

    with pytest.raises(PlynthError):
        orch.execute()

    assert state_path.exists()
    on_disk = StateFile.model_validate(yaml.safe_load(state_path.read_text(encoding="utf-8")))
    assert on_disk.phases[PHASE_1_PROJECT_AND_FIELDS].completed is False
    assert on_disk.phases[PHASE_1_PROJECT_AND_FIELDS].error == "network fell over"


def test_unhandled_exception_checkpoint_also_persisted(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Same checkpoint guarantee for the broad-Exception branch — that's
    the whole point of writing state before re-raising in both branches."""
    state_path = tmp_path / "state.yaml"
    orch, _ = _make_orchestrator(mocker, state_path)
    mocker.patch.object(
        orch,
        "phase_1_create_project_and_fields",
        side_effect=ValueError("bad data"),
    )

    with pytest.raises(ValueError):
        orch.execute()

    on_disk = StateFile.model_validate(yaml.safe_load(state_path.read_text(encoding="utf-8")))
    assert on_disk.phases[PHASE_1_PROJECT_AND_FIELDS].error == "ValueError: bad data"
