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


def permission_denied_message(display_target: str, operation: str) -> str:
    """Standard 403 advice when the token is valid but lacks permissions.

    GitHub returns 403 for two unrelated cases: rate-limit / abuse detection
    (handled in ``api_base.is_rate_limited_403``) and permission denials.
    When the response carries no rate-limit signal, the token is authenticated
    but the permission set is wrong, which the retry loop can never fix.
    Surface that as ``AuthError`` with a pointer at SECURITY.md so the user
    isn't told "max retries exceeded" for a permanent condition.

    ``operation`` describes the call that was denied (e.g. "creating
    milestone", "GraphQL mutation") so the user can map the failure to the
    permission row in SECURITY.md.
    """
    return (
        f"Permission denied by {display_target} on {operation}: the token is "
        f"authenticated but lacks the required permissions. plynth needs "
        f"repository Issues: Read and write plus organization Projects: Read "
        f"and write (fine-grained PAT), `repo` + `project` scopes (classic "
        f"PAT), or the equivalent installation permissions (GitHub App). See "
        f"SECURITY.md#token-handling."
    )


__all__ = [
    "PlynthError",
    "AuthError",
    "NotFoundError",
    "NetworkError",
    "ConfigError",
    "token_rejected_message",
    "permission_denied_message",
]
