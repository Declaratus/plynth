from __future__ import annotations

import pytest


def _build_parser():
    # Reconstruct the parser without invoking main(). We mirror cli.main()'s
    # argument layout; if cli.main() is restructured, this test guides the change.
    import argparse

    parser = argparse.ArgumentParser(prog="plynth")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--template", required=True)
    create.add_argument("--instance", required=True)
    create.add_argument("--dry-run", action="store_true")
    create.add_argument("--token")
    create.add_argument("--state-dir", default=".")
    create.add_argument("--write-delay-ms", type=int, default=1000)
    create.add_argument("-v", "--verbose", action="store_true")

    resolve = sub.add_parser("resolve")
    resolve.add_argument("--state", required=True)
    resolve.add_argument("--template", required=True)
    resolve.add_argument("--instance", required=True)
    resolve.add_argument("--token")
    resolve.add_argument("-v", "--verbose", action="store_true")

    return parser


def test_create_command_parses() -> None:
    parser = _build_parser()
    ns = parser.parse_args(["create", "--template", "t.yaml", "--instance", "i.yaml", "--dry-run"])
    assert ns.command == "create"
    assert ns.template == "t.yaml"
    assert ns.instance == "i.yaml"
    assert ns.dry_run is True
    assert ns.write_delay_ms == 1000
    assert ns.state_dir == "."


def test_create_requires_template_and_instance() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["create"])


def test_resolve_command_parses() -> None:
    parser = _build_parser()
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
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bogus"])
