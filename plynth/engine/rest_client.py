from __future__ import annotations

import requests

from plynth.engine.api_base import GHESClient
from plynth.errors import AuthError, NetworkError, NotFoundError


class RESTClient:
    """REST client for GHES operations not available in GraphQL."""

    def __init__(self, base: GHESClient) -> None:
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

        url = f"{self.base.ghes_url}/api/v3/repos/{owner}/{repo}/milestones"
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
                raise NetworkError(f"Could not connect to {self.base.ghes_url}: {e}") from e

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
                    f"Token rejected by {self.base.ghes_url}; verify GHES_TOKEN "
                    f"scopes include `repo` and `project`."
                )
            if response.status_code == 404:
                raise NotFoundError(f"Repository {owner}/{repo} not found on {self.base.ghes_url}")

            if not self.base._handle_retry(response, attempt):
                response.raise_for_status()

        raise NetworkError(
            f"Max retries ({self.base.max_retries}) exceeded creating milestone '{title}'"
        )
