from __future__ import annotations

import pytest

from plynth.cli import build_parser


def test_create_command_parses() -> None:
    parser = build_parser()
    ns = parser.parse_args(["create", "--template", "t.yaml", "--instance", "i.yaml", "--dry-run"])
    assert ns.command == "create"
    assert ns.template == "t.yaml"
    assert ns.instance == "i.yaml"
    assert ns.dry_run is True
    assert ns.write_delay_ms == 1000
    assert ns.state_dir == "."


def test_create_requires_template_and_instance() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["create"])


def test_resolve_command_parses() -> None:
    parser = build_parser()
    ns = parser.parse_args(
        [
            "resolve",
            "--state",
            "s.yaml",
            "--template",
            "t.yaml",
            "--instance",
            "i.yaml",
        ]
    )
    assert ns.command == "resolve"
    assert ns.state == "s.yaml"


def test_unknown_subcommand_rejected() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bogus"])


def test_timeout_seconds_rejects_zero() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "create",
                "--template",
                "t.yaml",
                "--instance",
                "i.yaml",
                "--timeout-seconds",
                "0",
            ]
        )


def test_timeout_seconds_rejects_negative() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "create",
                "--template",
                "t.yaml",
                "--instance",
                "i.yaml",
                "--timeout-seconds",
                "-5",
            ]
        )


def test_timeout_seconds_accepts_positive() -> None:
    parser = build_parser()
    ns = parser.parse_args(
        [
            "create",
            "--template",
            "t.yaml",
            "--instance",
            "i.yaml",
            "--timeout-seconds",
            "60",
        ]
    )
    assert ns.timeout_seconds == 60


def test_write_delay_ms_accepts_zero() -> None:
    parser = build_parser()
    ns = parser.parse_args(
        ["create", "--template", "t.yaml", "--instance", "i.yaml", "--write-delay-ms", "0"]
    )
    assert ns.write_delay_ms == 0


def test_write_delay_ms_accepts_upper_bound() -> None:
    parser = build_parser()
    ns = parser.parse_args(
        ["create", "--template", "t.yaml", "--instance", "i.yaml", "--write-delay-ms", "30000"]
    )
    assert ns.write_delay_ms == 30_000


def test_write_delay_ms_rejects_negative() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["create", "--template", "t.yaml", "--instance", "i.yaml", "--write-delay-ms", "-1"]
        )


def test_write_delay_ms_rejects_above_upper_bound() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["create", "--template", "t.yaml", "--instance", "i.yaml", "--write-delay-ms", "30001"]
        )


def test_format_defaults_to_text() -> None:
    parser = build_parser()
    ns = parser.parse_args(["create", "--template", "t.yaml", "--instance", "i.yaml", "--dry-run"])
    assert ns.format == "text"


def test_format_accepts_json() -> None:
    parser = build_parser()
    ns = parser.parse_args(
        [
            "create",
            "--template",
            "t.yaml",
            "--instance",
            "i.yaml",
            "--dry-run",
            "--format",
            "json",
        ]
    )
    assert ns.format == "json"


def test_format_rejects_unknown_value() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "create",
                "--template",
                "t.yaml",
                "--instance",
                "i.yaml",
                "--dry-run",
                "--format",
                "yaml",
            ]
        )
