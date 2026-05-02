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
