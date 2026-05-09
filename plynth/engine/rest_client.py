from __future__ import annotations

import requests

from plynth.engine.api_base import GitHubClient
from plynth.errors import AuthError, NetworkError, NotFoundError


class RESTClient:
    """REST client for GitHub operations not available in GraphQL."""

    def __init__(self, base: GitHubClient) -> None:
        self.base = base

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
                raise AuthError(
                    f"Token rejected by {self.base.display_target}; verify PLYNTH_TOKEN "
                    f"scopes include `repo` and `project`."
                )
            if response.status_code == 404:
                raise NotFoundError(
                    f"Repository {owner}/{repo} not found on {self.base.display_target}"
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
                    f"requires `repo` (classic) or organization Administration: write "
                    f"(fine-grained)."
                )
            if response.status_code == 404:
                raise NotFoundError(f"Organization {org} not found on {self.base.display_target}")

            if not self.base._handle_retry(response, attempt):
                response.raise_for_status()

        raise NetworkError(
            f"Max retries ({self.base.max_retries}) exceeded creating repo '{org}/{name}'"
        )
