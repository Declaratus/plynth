from __future__ import annotations

from plynth.models.state import (
    PHASE_1_PROJECT_AND_FIELDS,
    PHASE_3_ISSUES,
    StateFile,
)


def test_default_schema_version() -> None:
    s = StateFile()
    assert s.schema_version == "1.0"


def test_phase_complete_helpers() -> None:
    s = StateFile()
    assert not s.is_phase_complete(PHASE_1_PROJECT_AND_FIELDS)

    s.mark_phase_complete(PHASE_1_PROJECT_AND_FIELDS)
    assert s.is_phase_complete(PHASE_1_PROJECT_AND_FIELDS)
    assert s.phases[PHASE_1_PROJECT_AND_FIELDS].completed_at is not None
    assert s.phases[PHASE_1_PROJECT_AND_FIELDS].error is None


def test_phase_error_recorded() -> None:
    s = StateFile()
    s.mark_phase_error(PHASE_3_ISSUES, "boom")
    assert s.phases[PHASE_3_ISSUES].error == "boom"
    assert s.phases[PHASE_3_ISSUES].completed is False
    assert not s.is_phase_complete(PHASE_3_ISSUES)


def test_touch_updates_timestamp() -> None:
    s = StateFile()
    assert s.updated_at == ""
    s.touch()
    assert s.updated_at != ""


def test_roundtrip_through_model_dump() -> None:
    s = StateFile(org="example-org", ghes_url="https://ghes.example.com")
    s.mark_phase_complete(PHASE_1_PROJECT_AND_FIELDS)
    dumped = s.model_dump()
    rebuilt = StateFile.model_validate(dumped)
    assert rebuilt.org == "example-org"
    assert rebuilt.is_phase_complete(PHASE_1_PROJECT_AND_FIELDS)
