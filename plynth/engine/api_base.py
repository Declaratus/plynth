from __future__ import annotations

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

    @property
    def display_target(self) -> str:
        """Human-readable target for diagnostics. Empty string → 'github.com'."""
        return self.target if self.target else "github.com"

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

        Returns True if the caller should retry the request.
        """
        if response.status_code in (429, 403, 502, 503):
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                time.sleep(float(retry_after))
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
