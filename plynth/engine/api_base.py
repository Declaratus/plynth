from __future__ import annotations

import logging
import time
import warnings
from importlib import metadata

import requests


def derive_api_roots(target: str) -> tuple[str, str]:
    """Return (graphql_endpoint, rest_base) for a target.

    - "" or "github.com" → ("https://api.github.com/graphql", "https://api.github.com")
    - "https://api.github.com" → same as github.com
    - "https://<other>" → ("{base}/api/graphql", "{base}/api/v3")

    Trailing slashes on the input are tolerated. Bare hostnames other than
    ``github.com``, ``http://`` URLs, and ``https://github.com`` (the web host,
    not the API host) are rejected with a fix-it message.
    """
    stripped = target.rstrip("/")

    # github.com special cases — both the empty default and explicit forms.
    if stripped in ("", "github.com", "https://api.github.com"):
        return ("https://api.github.com/graphql", "https://api.github.com")

    # https://github.com is the web host, not an API host. Don't auto-correct;
    # the user has likely misconfigured something and we want them to notice.
    if stripped == "https://github.com":
        raise ValueError(
            "target 'https://github.com' is not valid: GitHub.com's API host "
            "is api.github.com. Use target: github.com or "
            "target: https://api.github.com."
        )

    # http:// is never acceptable for either GHES or github.com.
    if stripped.startswith("http://"):
        raise ValueError(
            f"target '{target}' is not valid: only https:// targets are "
            f"supported. Use https:// instead of http://."
        )

    # Anything else must be an https:// URL. Bare hostnames like
    # 'github.example.com' or paths like 'api.github.com' (no scheme) fall
    # through to here and are rejected.
    if not stripped.startswith("https://"):
        raise ValueError(
            f"target '{target}' is not valid: must be empty, 'github.com', "
            f"or an https:// URL (e.g. 'https://ghes.example.com')."
        )

    return (f"{stripped}/api/graphql", f"{stripped}/api/v3")


# GitHub uses 403 for two unrelated cases: rate limit / abuse detection
# (retryable) and permission denial (not retryable). The signals below are
# the canonical rate-limit shapes from GitHub's REST docs; their absence
# means a permission denial that the retry loop can't fix.
_SECONDARY_RATE_LIMIT_PHRASES = ("secondary rate limit", "abuse detection")


def is_rate_limited_403(response: requests.Response) -> bool:
    """True iff a 403 response carries a positive rate-limit signal.

    Checks three places, any one of which is enough: ``Retry-After`` header,
    ``X-RateLimit-Remaining: 0`` (primary rate limit), or one of the
    secondary-rate-limit phrases in the response body's ``message``.
    """
    if response.headers.get("Retry-After"):
        return True
    if response.headers.get("X-RateLimit-Remaining") == "0":
        return True
    try:
        message = (response.json() or {}).get("message", "")
    except ValueError:
        message = ""
    lower = message.lower() if isinstance(message, str) else ""
    return any(phrase in lower for phrase in _SECONDARY_RATE_LIMIT_PHRASES)


class GitHubClient:
    """Base HTTP client for GitHub.com or GHES with rate limiting and retry."""

    def __init__(
        self,
        target: str,
        token: str,
        write_delay_ms: int = 1000,
        max_retries: int = 3,
        request_timeout_s: int = 30,
    ):
        self.target = target
        self.graphql_endpoint, self.rest_base = derive_api_roots(target)
        self.session = requests.Session()
        try:
            version = metadata.version("plynth")
        except metadata.PackageNotFoundError:
            version = "0.0.0"
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": f"plynth/{version}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        self.write_delay_ms = write_delay_ms
        self.max_retries = max_retries
        self.request_timeout_s = request_timeout_s
        self._last_write_time: float = 0.0
        # Populated by RESTClient.detect_installed_version() for GHES targets.
        # Stays None on github.com (no /meta version) and on detection failure.
        self.installed_version: tuple[int, int] | None = None

    @property
    def display_target(self) -> str:
        """Human-readable target for diagnostics. Empty string → 'github.com'."""
        return self.target if self.target else "github.com"

    @property
    def is_ghes(self) -> bool:
        """True if the target is a GHES instance (not github.com / api.github.com).

        Normalizes the trailing slash to match `derive_api_roots`, which
        tolerates `github.com/` and `https://api.github.com/`. Without this,
        the trailing-slash variants would route to `/meta` probing.
        """
        return self.target.rstrip("/") not in ("", "github.com", "https://api.github.com")

    def warn_if_below(
        self,
        min_version: tuple[int, int],
        feature: str,
        log: logging.Logger,
    ) -> None:
        """Log a warning if the GHES version is known and below `min_version`.

        github.com (where `installed_version` is None) is treated as latest and
        never warns. A failed detection (also None) is silent because the
        detection itself logged the failure; warning here would double up.
        """
        if self.installed_version is None:
            return
        if self.installed_version < min_version:
            have = f"{self.installed_version[0]}.{self.installed_version[1]}"
            need = f"{min_version[0]}.{min_version[1]}"
            log.warning(
                f"Feature '{feature}' requires GHES {need}+, detected {have}. "
                f"Continuing; the feature may be skipped or fail at the API."
            )

    def _wait_for_write_delay(self) -> None:
        """Enforce minimum delay between mutating calls."""
        elapsed = time.time() - self._last_write_time
        remaining = (self.write_delay_ms / 1000.0) - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _record_write(self) -> None:
        """Record timestamp after a mutating call."""
        self._last_write_time = time.time()

    def _handle_retry(self, response: requests.Response, attempt: int) -> bool:
        """Check if we should retry based on rate limit headers.

        Returns True if the caller should retry the request. A 403 only
        counts as retryable when ``is_rate_limited_403`` confirms a rate
        limit shape; permission-denied 403s fall through so the caller can
        raise ``AuthError`` instead of spinning the retry loop.
        """
        if response.status_code == 403 and not is_rate_limited_403(response):
            return False
        if response.status_code in (429, 403, 502, 503):
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                time.sleep(min(float(retry_after), 60.0))
            else:
                time.sleep(2**attempt)
            return True
        return False


class GHESClient(GitHubClient):
    """Deprecated alias for :class:`GitHubClient`. Will be removed in v0.4.0."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        warnings.warn(
            "GHESClient is deprecated; use GitHubClient instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
