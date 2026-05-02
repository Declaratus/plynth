"""plynth CLI -- GitHub Projects as Code."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import ValidationError

from plynth.engine.api_base import GHESClient
from plynth.engine.graphql_client import GraphQLClient
from plynth.engine.phases import PhaseOrchestrator
from plynth.engine.planner import format_dry_run, plan
from plynth.engine.rest_client import RESTClient
from plynth.errors import ConfigError, PlynthError
from plynth.models.instance import InstanceConfig
from plynth.models.state import (
    PHASE_5_REFERENCES_AND_DEPS,
    InstanceRef,
    RepoState,
    StateFile,
    TemplateRef,
)
from plynth.models.template import TemplateDefinition


def _positive_int(value: str) -> int:
    """argparse type for flags that must be a positive integer."""
    try:
        ivalue = int(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"expected integer, got '{value}'") from e
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {ivalue}")
    return ivalue


def build_parser() -> argparse.ArgumentParser:
    """Build the plynth argparse parser. Exposed for test reuse."""
    parser = argparse.ArgumentParser(
        prog="plynth",
        description=("GitHub Projects as Code -- bootstrap GitHub Projects from YAML templates."),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- create command ---
    create_parser = subparsers.add_parser("create", help="Create a new project from template")
    create_parser.add_argument("--template", required=True, help="Path to template YAML")
    create_parser.add_argument("--instance", required=True, help="Path to instance config YAML")
    create_parser.add_argument(
        "--dry-run", action="store_true", help="Print plan without executing"
    )
    create_parser.add_argument("--token", help="GHES PAT (or set GHES_TOKEN env var)")
    create_parser.add_argument("--state-dir", default=".", help="Directory for state file output")
    create_parser.add_argument(
        "--write-delay-ms",
        type=int,
        default=1000,
        help="Delay between API writes (ms)",
    )
    create_parser.add_argument(
        "--timeout-seconds",
        type=_positive_int,
        default=30,
        help="Per-request HTTP timeout (seconds, default 30, must be > 0)",
    )
    create_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    # --- resolve command ---
    resolve_parser = subparsers.add_parser(
        "resolve", help="Re-resolve cross-references from state file"
    )
    resolve_parser.add_argument("--state", required=True, help="Path to existing state file")
    resolve_parser.add_argument("--template", required=True, help="Path to template YAML")
    resolve_parser.add_argument("--instance", required=True, help="Path to instance config YAML")
    resolve_parser.add_argument("--token", help="GHES PAT (or set GHES_TOKEN env var)")
    resolve_parser.add_argument(
        "--timeout-seconds",
        type=_positive_int,
        default=30,
        help="Per-request HTTP timeout (seconds, default 30, must be > 0)",
    )
    resolve_parser.add_argument("-v", "--verbose", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("plynth")

    try:
        if args.command == "create":
            _cmd_create(args, log)
        elif args.command == "resolve":
            _cmd_resolve(args, log)
    except PlynthError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


def _cmd_create(args: argparse.Namespace, log: logging.Logger) -> None:
    """Execute the 'create' command."""
    # 1. Load and parse YAML
    template = _load_template(args.template)
    instance = _load_instance(args.instance)

    # 2. Plan
    execution_plan = plan(template, instance)

    # 3. Dry run?
    if args.dry_run:
        print(format_dry_run(execution_plan))
        return

    # 4. Get token
    token = _get_token(args)

    # 5. Initialize clients
    base = GHESClient(
        instance.ghes_url,
        token,
        write_delay_ms=args.write_delay_ms,
        request_timeout_s=args.timeout_seconds,
    )
    gql = GraphQLClient(base)
    rest = RESTClient(base)

    # 6. Initialize or resume state file
    state_path = Path(args.state_dir) / f"{_slugify(execution_plan.project_name)}.plynth-state.yaml"
    state = _init_or_load_state(state_path, args.template, args.instance, instance, log)

    # 7. Execute
    orchestrator = PhaseOrchestrator(
        plan=execution_plan,
        gql=gql,
        rest=rest,
        state=state,
        state_path=state_path,
        logger=log,
    )
    orchestrator.execute()

    log.info(f"State file written to: {state_path}")


def _cmd_resolve(args: argparse.Namespace, log: logging.Logger) -> None:
    """Execute the 'resolve' command -- re-run Phase 5 only."""
    template = _load_template(args.template)
    instance = _load_instance(args.instance)
    execution_plan = plan(template, instance)

    token = _get_token(args)
    base = GHESClient(instance.ghes_url, token, request_timeout_s=args.timeout_seconds)
    gql = GraphQLClient(base)
    rest = RESTClient(base)

    # Load existing state
    state = _load_state(Path(args.state))

    # Reset Phase 5 so it re-runs
    state.phases.pop(PHASE_5_REFERENCES_AND_DEPS, None)

    orchestrator = PhaseOrchestrator(
        plan=execution_plan,
        gql=gql,
        rest=rest,
        state=state,
        state_path=Path(args.state),
        logger=log,
    )
    # Only run Phase 5
    orchestrator.phase_5_resolve_references_and_dependencies()
    state.mark_phase_complete(PHASE_5_REFERENCES_AND_DEPS)
    orchestrator._save_state()
    log.info("Re-resolve complete.")


def _load_template(path: str) -> TemplateDefinition:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"Template file not found: {path}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in template '{path}': {e}") from e
    try:
        return TemplateDefinition.model_validate(data)
    except ValidationError as e:
        raise ConfigError(f"Template '{path}' failed schema validation:\n{e}") from e


def _load_instance(path: str) -> InstanceConfig:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"Instance file not found: {path}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in instance '{path}': {e}") from e
    try:
        return InstanceConfig.model_validate(data)
    except ValidationError as e:
        raise ConfigError(f"Instance '{path}' failed schema validation:\n{e}") from e


def _load_state(path: Path) -> StateFile:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"State file not found: {path}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in state file '{path}': {e}") from e
    try:
        return StateFile.model_validate(data)
    except ValidationError as e:
        raise ConfigError(f"State file '{path}' failed schema validation:\n{e}") from e


def _get_token(args: argparse.Namespace) -> str:
    token = getattr(args, "token", None) or os.environ.get("GHES_TOKEN")
    if not token:
        print(
            "Error: provide --token or set GHES_TOKEN environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)
    return token


def _init_or_load_state(
    state_path: Path,
    template_path: str,
    instance_path: str,
    instance: InstanceConfig,
    log: logging.Logger,
) -> StateFile:
    """Initialize a new state file or load existing one for resume."""
    template_hash = _file_hash(template_path)
    instance_hash = _file_hash(instance_path)

    if state_path.exists():
        log.info(f"Found existing state file: {state_path}")
        state = _load_state(state_path)

        # Guard: template hash must match for resume
        if state.template_sha256 and state.template_sha256 != template_hash:
            print(
                f"Error: template has changed since the state file was "
                f"created.\n"
                f"  State template hash:   {state.template_sha256}\n"
                f"  Current template hash: {template_hash}\n"
                f"Delete the state file to start fresh, or use a new "
                f"state directory.",
                file=sys.stderr,
            )
            sys.exit(1)

        return state

    # New state file
    state = StateFile(
        created_at=datetime.now(timezone.utc).isoformat(),
        template_sha256=template_hash,
        instance_sha256=instance_hash,
        template=TemplateRef(file=template_path, version=""),
        instance=InstanceRef(file=instance_path, config_hash=instance_hash),
        ghes_url=instance.ghes_url,
        org=instance.org,
        repo=RepoState(name=instance.repo.name),
    )
    return state


def _file_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _slugify(text: str) -> str:
    """Convert project name to filesystem-safe slug."""
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug
