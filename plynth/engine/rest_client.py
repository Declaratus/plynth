from __future__ import annotations

import logging

import requests

from plynth.engine.api_base import GitHubClient, is_rate_limited_403
from plynth.errors import (
    AuthError,
    NetworkError,
    NotFoundError,
    permission_denied_message,
    token_rejected_message,
)


class RESTClient:
    """REST client for GitHub operations not available in GraphQL."""

    def __init__(self, base: GitHubClient) -> None:
        self.base = base

    def detect_installed_version(self, log: logging.Logger | None = None) -> None:
        """GET `{rest_base}/meta` and cache the parsed version on `base`.

        No-op for github.com targets — `/meta` exists but doesn't return an
        installed_version, and version-gating against github.com is meaningless
        anyway (it always has the latest features). For GHES targets, sets
        `base.installed_version` to a `(major, minor)` tuple, or leaves it None
        on any kind of failure (network, non-2xx, missing/malformed field).
        Failures are logged at WARNING but never raised: version detection is
        informational, not gating.
        """
        if not self.base.is_ghes:
            return

        url = f"{self.base.rest_base}/meta"
        try:
            response = self.base.session.get(url, timeout=self.base.request_timeout_s)
        except requests.RequestException as e:
            # Detection is informational and must not abort startup. Catch the
            # full requests hierarchy (Timeout, ConnectionError, SSLError,
            # InvalidURL, …) so any transport-layer failure produces a warning
            # and a None version, not a stack trace from `plynth create`.
            if log is not None:
                log.warning(f"Could not reach {url} for version detection: {e}")
            return

        if not response.ok:
            if log is not None:
                log.warning(
                    f"{url} returned HTTP {response.status_code}; skipping version detection."
                )
            return

        try:
            raw = response.json().get("installed_version")
        except ValueError:
            if log is not None:
                log.warning(f"{url} returned non-JSON body; skipping version detection.")
            return

        parsed = _parse_version(raw)
        if parsed is None:
            if log is not None:
                log.warning(
                    f"{url} response missing or malformed installed_version "
                    f"(got {raw!r}); skipping version detection."
                )
            return

        self.base.installed_version = parsed
        if log is not None:
            log.info(f"Detected GHES {parsed[0]}.{parsed[1]} at {self.base.display_target}")

    def create_milestone(
        self,
        owner: str,
        repo: str,
        title: str,
        description: str = "",
        due_on: str | None = None,
    ) -> dict:
        """Create a repository milestone.

        due_on: ISO 8601 date string (e.g., "2026-04-06T00:00:00Z")

        Returns: {"number": 3, "node_id": "MI_...", "title": "..."}
        """
        self.base._wait_for_write_delay()

        url = f"{self.base.rest_base}/repos/{owner}/{repo}/milestones"
        payload: dict = {"title": title, "description": description}
        if due_on:
            payload["due_on"] = due_on

        for attempt in range(self.base.max_retries):
            try:
                response = self.base.session.post(
                    url, json=payload, timeout=self.base.request_timeout_s
                )
            except requests.Timeout as e:
                raise NetworkError(
                    f"REST request to {url} timed out after {self.base.request_timeout_s}s"
                ) from e
            except requests.ConnectionError as e:
                raise NetworkError(f"Could not connect to {self.base.display_target}: {e}") from e

            if response.ok:
                self.base._record_write()
                data = response.json()
                return {
                    "number": data["number"],
                    "node_id": data["node_id"],
                    "title": data["title"],
                }

            if response.status_code == 401:
                raise AuthError(token_rejected_message(self.base.display_target))
            if response.status_code == 404:
                raise NotFoundError(
                    f"Repository {owner}/{repo} not found on {self.base.display_target}"
                )
            if response.status_code == 403 and not is_rate_limited_403(response):
                raise AuthError(
                    permission_denied_message(
                        self.base.display_target, f"creating milestone '{title}'"
                    )
                )

            if not self.base._handle_retry(response, attempt):
                response.raise_for_status()

        raise NetworkError(
            f"Max retries ({self.base.max_retries}) exceeded creating milestone '{title}'"
        )

    def create_repo(self, org: str, name: str) -> dict:
        """Create a private repository in `org`.

        Used by Phase 1 when `repo.create: true` and the target repo does not
        yet exist. Created private by design: plynth bootstraps internal
        project tracking, and a public default would be a surprise.

        Requires permissions beyond the standard plynth set: classic `repo`
        scope already covers it, but a fine-grained PAT also needs the
        organization `Administration: Read and write` permission. See
        SECURITY.md.

        Returns: {"node_id": "R_...", "name": "..."}
        """
        self.base._wait_for_write_delay()

        url = f"{self.base.rest_base}/orgs/{org}/repos"
        payload = {"name": name, "private": True}

        for attempt in range(self.base.max_retries):
            try:
                response = self.base.session.post(
                    url, json=payload, timeout=self.base.request_timeout_s
                )
            except requests.Timeout as e:
                raise NetworkError(
                    f"REST request to {url} timed out after {self.base.request_timeout_s}s"
                ) from e
            except requests.ConnectionError as e:
                raise NetworkError(f"Could not connect to {self.base.display_target}: {e}") from e

            if response.ok:
                self.base._record_write()
                data = response.json()
                return {"node_id": data["node_id"], "name": data["name"]}

            if response.status_code == 401:
                raise AuthError(
                    f"Token rejected by {self.base.display_target}; creating a repo "
                    f"requires `repo` (classic) or organization Administration: Read and write "
                    f"(fine-grained)."
                )
            if response.status_code == 404:
                raise NotFoundError(f"Organization {org} not found on {self.base.display_target}")
            if response.status_code == 403 and not is_rate_limited_403(response):
                raise AuthError(
                    f"Permission denied by {self.base.display_target} creating repo "
                    f"'{org}/{name}': the token is authenticated but lacks the required "
                    f"permissions. Repo creation needs `repo` (classic) or organization "
                    f"Administration: Read and write (fine-grained). See SECURITY.md."
                )

            if not self.base._handle_retry(response, attempt):
                response.raise_for_status()

        raise NetworkError(
            f"Max retries ({self.base.max_retries}) exceeded creating repo '{org}/{name}'"
        )


def _parse_version(raw: object) -> tuple[int, int] | None:
    """Parse a `installed_version` string ("3.20.1") to `(major, minor)`.

    Patch is ignored — feature gating runs at minor granularity. Anything
    not parseable returns None.
    """
    if not isinstance(raw, str):
        return None
    parts = raw.split(".")
    if len(parts) < 2:
        return None
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return None
