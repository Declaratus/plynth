from __future__ import annotations

from plynth.engine.api_base import GHESClient


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
            response = self.base.session.post(url, json=payload)
            if response.ok:
                self.base._record_write()
                data = response.json()
                return {
                    "number": data["number"],
                    "node_id": data["node_id"],
                    "title": data["title"],
                }
            if not self.base._handle_retry(response, attempt):
                response.raise_for_status()

        raise RuntimeError(f"Max retries exceeded creating milestone '{title}'")
