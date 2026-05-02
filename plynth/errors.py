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


__all__ = [
    "PlynthError",
    "AuthError",
    "NotFoundError",
    "NetworkError",
    "ConfigError",
]
