"""plynth error hierarchy.

User-facing exceptions raised by the engine and CLI. The CLI's top-level
handler prints `Error: {e}` and exits 2 for any subclass of `PlynthError`,
so prefer raising one of these over generic `Exception` for actionable
failures.
"""

from __future__ import annotations


class PlynthError(Exception):
    """Base class for all plynth user-facing errors."""


class AuthError(PlynthError):
    """Token rejected (HTTP 401) or insufficient scopes."""


class NotFoundError(PlynthError):
    """A referenced GitHub resource (org, repo, project) does not exist."""


class NetworkError(PlynthError):
    """Connection failure, timeout, or other transport-level error."""


class ConfigError(PlynthError):
    """Local configuration problem: missing file, invalid YAML, schema error."""


def token_rejected_message(display_target: str) -> str:
    """Standard 401 advice for the GraphQL and REST clients.

    Single source of truth for the wording so the runtime message can't
    drift away from SECURITY.md. The two PAT shapes named here mirror the
    SECURITY.md "Token shapes" section verbatim — adjust both at once.
    """
    return (
        f"Token rejected by {display_target}; verify PLYNTH_TOKEN has either "
        f"classic `repo` + `project` scopes or a fine-grained PAT with "
        f"repository Issues (Read and write) plus organization Projects "
        f"(Read and write). See SECURITY.md for the full permission breakdown."
    )


__all__ = [
    "PlynthError",
    "AuthError",
    "NotFoundError",
    "NetworkError",
    "ConfigError",
    "token_rejected_message",
]
