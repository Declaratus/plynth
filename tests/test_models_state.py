from __future__ import annotations

from pathlib import Path

import yaml

from plynth.models.state import (
    PHASE_1_PROJECT_AND_FIELDS,
    PHASE_3_ISSUES,
    StateFile,
)

FIXTURES = Path(__file__).parent / "fixtures"


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
    s = StateFile(org="example-org", target="https://ghes.example.com")
    s.mark_phase_complete(PHASE_1_PROJECT_AND_FIELDS)
    dumped = s.model_dump()
    rebuilt = StateFile.model_validate(dumped)
    assert rebuilt.org == "example-org"
    assert rebuilt.is_phase_complete(PHASE_1_PROJECT_AND_FIELDS)


def test_legacy_ghes_url_key_silently_migrated() -> None:
    """v0.2.0 state files used `ghes_url:`. State files are machine-written, so
    a hard rename would gratuitously break in-flight runs. Verify the silent
    migration in the model_validator(mode='before') hook."""
    legacy_dump = {
        "schema_version": "1.0",
        "ghes_url": "https://ghes.example.com",
        "org": "example-org",
    }
    s = StateFile.model_validate(legacy_dump)
    assert s.target == "https://ghes.example.com"
    assert s.org == "example-org"


def test_legacy_ghes_url_does_not_override_target_if_both_present() -> None:
    """Defensive: if both keys are somehow present, prefer the new `target` key."""
    data = {
        "schema_version": "1.0",
        "ghes_url": "https://old.example.com",
        "target": "https://new.example.com",
        "org": "example-org",
    }
    s = StateFile.model_validate(data)
    assert s.target == "https://new.example.com"


# ── #45: schema_version cadence ────────────────────────────────────


def test_v0_3_state_fixture_round_trips() -> None:
    """A hand-written v0.3-era state file (pre-M1 shape) must load cleanly
    under the current schema and survive a model_dump / model_validate cycle
    without losing data. Regression guard for the compat-shim layer in
    ``StateFile._apply_compat_shims``."""
    raw = yaml.safe_load((FIXTURES / "v0_3-state.yaml").read_text(encoding="utf-8"))
    loaded = StateFile.model_validate(raw)

    assert loaded.schema_version == "1.0"
    assert loaded.target == "https://ghes.example.com"
    assert loaded.org == "example-org"
    assert loaded.repo is not None and loaded.repo.name == "acme-service"
    assert loaded.project is not None and loaded.project.number == 12
    assert "workstream" in loaded.fields
    assert loaded.fields["workstream"].options["Documentation"] == "opt_doc"
    assert loaded.milestones["M1"].number == 3
    assert loaded.issues["001"].number == 47
    assert loaded.is_phase_complete(PHASE_1_PROJECT_AND_FIELDS)
    assert not loaded.is_phase_complete(PHASE_3_ISSUES)
    assert loaded.phases[PHASE_3_ISSUES].error == "Connection reset by peer"
    # M1+ field absent from the v0.3 fixture must zero-fill cleanly.
    assert loaded.status_field_id is None

    # Dump and reload to confirm the result is itself a valid StateFile dict.
    rebuilt = StateFile.model_validate(loaded.model_dump())
    assert rebuilt.model_dump() == loaded.model_dump()
