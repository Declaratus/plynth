from __future__ import annotations

import time

import requests


class GHESClient:
    """Base HTTP client for GHES with rate limiting and retry."""

    def __init__(
        self,
        ghes_url: str,
        token: str,
        write_delay_ms: int = 1000,
        max_retries: int = 3,
    ):
        self.ghes_url = ghes_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )
        self.write_delay_ms = write_delay_ms
        self.max_retries = max_retries
        self._last_write_time: float = 0.0

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
