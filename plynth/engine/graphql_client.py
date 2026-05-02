from __future__ import annotations

import requests

from plynth.engine.api_base import GitHubClient
from plynth.errors import AuthError, NetworkError, NotFoundError, PlynthError
from plynth.queries import mutations, queries


class GraphQLError(PlynthError):
    """Raised when a GraphQL response contains errors."""

    def __init__(self, errors: list[dict]) -> None:
        self.errors = errors
        messages = [e.get("message", str(e)) for e in errors]
        super().__init__(f"GraphQL errors: {'; '.join(messages)}")


def _classify_graphql_errors(errors: list[dict], display_target: str) -> PlynthError:
    """Map GraphQL `errors[]` entries to a friendly PlynthError subclass."""
    for err in errors:
        msg = err.get("message", "")
        if "Could not resolve to" in msg or "could not be found" in msg.lower():
            return NotFoundError(f"{msg.rstrip('.')} (target: {display_target})")
    return GraphQLError(errors)


class GraphQLClient:
    """GraphQL client for GitHub Projects V2 and Issues API."""

    def __init__(self, base: GitHubClient) -> None:
        self.base = base
        self.endpoint = base.graphql_endpoint

    def execute(
        self,
        query: str,
        variables: dict | None = None,
        *,
        is_mutation: bool = False,
    ) -> dict:
        """Execute a GraphQL query/mutation. Returns the 'data' dict or raises."""
        if is_mutation:
            self.base._wait_for_write_delay()

        for attempt in range(self.base.max_retries):
            try:
                response = self.base.session.post(
                    self.endpoint,
                    json={"query": query, "variables": variables or {}},
                    timeout=self.base.request_timeout_s,
                )
            except requests.Timeout as e:
                raise NetworkError(
                    f"GraphQL request to {self.base.display_target} timed out "
                    f"after {self.base.request_timeout_s}s"
                ) from e
            except requests.ConnectionError as e:
                raise NetworkError(f"Could not connect to {self.base.display_target}: {e}") from e

            if response.ok:
                result = response.json()
                if "errors" in result:
                    raise _classify_graphql_errors(result["errors"], self.base.display_target)
                if is_mutation:
                    self.base._record_write()
                return result["data"]

            if response.status_code == 401:
                raise AuthError(
                    f"Token rejected by {self.base.display_target}; verify PLYNTH_TOKEN "
                    f"scopes include `repo` and `project`."
                )

            if not self.base._handle_retry(response, attempt):
                response.raise_for_status()

        raise NetworkError(
            f"Max retries ({self.base.max_retries}) exceeded for GraphQL "
            f"call to {self.base.display_target}"
        )

    # ── Preflight queries ──────────────────────────────────

    def get_org_id(self, login: str) -> str:
        """Resolve org login to node ID."""
        data = self.execute(queries.GET_ORG_ID, {"login": login})
        return data["organization"]["id"]

    def get_repo_id(self, owner: str, name: str) -> str:
        """Resolve repo to node ID."""
        data = self.execute(queries.GET_REPO_ID, {"owner": owner, "name": name})
        return data["repository"]["id"]

    # ── Phase 1: Project + Fields ──────────────────────────

    def create_project(self, owner_id: str, title: str) -> dict:
        """Create a ProjectV2.

        Returns: {"id": "PVT_...", "number": 12, "url": "https://..."}
        """
        data = self.execute(
            mutations.CREATE_PROJECT,
            {"ownerId": owner_id, "title": title},
            is_mutation=True,
        )
        return data["createProjectV2"]["projectV2"]

    def create_field(
        self,
        project_id: str,
        name: str,
        data_type: str,
        options: list[dict] | None = None,
    ) -> dict:
        """Create a custom field on a project.

        data_type: "SINGLE_SELECT", "TEXT", "NUMBER", "DATE", "ITERATION"
        options: for SINGLE_SELECT, list of {"name": "...", "color": "...", "description": ""}

        Returns: {"id": "PVTSSF_...", "name": "..."}
        """
        variables: dict = {
            "projectId": project_id,
            "name": name,
            "dataType": data_type,
        }
        if options is not None:
            variables["options"] = options

        data = self.execute(mutations.CREATE_FIELD, variables, is_mutation=True)
        return data["createProjectV2Field"]["projectV2Field"]

    def get_project_fields(self, project_id: str) -> list[dict]:
        """Re-query all fields on a project to get field IDs and option IDs.

        Returns: list of field dicts, each containing:
          {"id": "...", "name": "...", "dataType": "...",
           "options": [{"id": "...", "name": "..."}]}  # for single-select
        """
        data = self.execute(queries.GET_PROJECT_FIELDS, {"projectId": project_id})
        return data["node"]["fields"]["nodes"]

    # ── Phase 3: Issue creation ────────────────────────────

    def create_issue(
        self,
        repository_id: str,
        title: str,
        body: str,
        milestone_id: str | None = None,
    ) -> dict:
        """Create a repository issue via GraphQL.

        Note: milestone_id here is the milestone NODE ID, not the number.

        Returns: {"id": "I_...", "number": 47, "title": "..."}
        """
        variables: dict = {
            "repositoryId": repository_id,
            "title": title,
            "body": body,
        }
        if milestone_id is not None:
            variables["milestoneId"] = milestone_id

        data = self.execute(mutations.CREATE_ISSUE, variables, is_mutation=True)
        return data["createIssue"]["issue"]

    # ── Phase 4: Project item management ───────────────────

    def add_item_to_project(self, project_id: str, content_id: str) -> str:
        """Add an issue to a project. Returns the project item ID.

        Returns: item_id string "PVTI_..."
        """
        data = self.execute(
            mutations.ADD_ITEM_TO_PROJECT,
            {"projectId": project_id, "contentId": content_id},
            is_mutation=True,
        )
        return data["addProjectV2ItemById"]["item"]["id"]

    def set_field_value(
        self,
        project_id: str,
        item_id: str,
        field_id: str,
        value: dict,
    ) -> None:
        """Set a field value on a project item.

        value format depends on field type:
          single_select: {"singleSelectOptionId": "option_id"}
          text: {"text": "value"}
          number: {"number": 123.0}
          date: {"date": "2026-04-01"}
          iteration: {"iterationId": "iter_id"}
        """
        self.execute(
            mutations.SET_FIELD_VALUE,
            {
                "projectId": project_id,
                "itemId": item_id,
                "fieldId": field_id,
                "value": value,
            },
            is_mutation=True,
        )

    # ── Phase 5: Cross-references + dependencies ───────────

    def update_issue_body(self, issue_id: str, body: str) -> None:
        """Update an issue's body text (for cross-reference resolution)."""
        self.execute(
            mutations.UPDATE_ISSUE_BODY,
            {"issueId": issue_id, "body": body},
            is_mutation=True,
        )

    def add_blocked_by(self, issue_id: str, blocking_issue_id: str) -> None:
        """Create a dependency: issue_id is blocked by blocking_issue_id."""
        self.execute(
            mutations.ADD_BLOCKED_BY,
            {"issueId": issue_id, "blockingIssueId": blocking_issue_id},
            is_mutation=True,
        )
