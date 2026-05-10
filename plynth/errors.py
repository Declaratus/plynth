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
    drift away from SECURITY.md. The three token shapes named here track
    the subsections under SECURITY.md ``## Token handling`` (Fine-grained
    PAT, Classic PAT, GitHub Apps) — keep this list in sync if a fourth
    shape ever lands.
    """
    return (
        f"Token rejected by {display_target}; verify PLYNTH_TOKEN has scopes "
        f"covering issue and project mutations. See SECURITY.md for supported "
        f"token shapes (classic PAT, fine-grained PAT, GitHub App)."
    )


__all__ = [
    "PlynthError",
    "AuthError",
    "NotFoundError",
    "NetworkError",
    "ConfigError",
    "token_rejected_message",
]
