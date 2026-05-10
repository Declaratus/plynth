from __future__ import annotations

import requests

from plynth.engine.api_base import GitHubClient, is_rate_limited_403
from plynth.errors import (
    AuthError,
    NetworkError,
    NotFoundError,
    PlynthError,
    permission_denied_message,
    token_rejected_message,
)
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
                raise AuthError(token_rejected_message(self.base.display_target))

            if response.status_code == 403 and not is_rate_limited_403(response):
                operation = "GraphQL mutation" if is_mutation else "GraphQL query"
                raise AuthError(
                    permission_denied_message(self.base.display_target, operation)
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

    # CRITICAL: ProjectV2 single-select option mutations (this method on
    # create, plus any future updateProjectV2Field-style call) replace the
    # full options list. Any option omitted from the input is DELETED, along
    # with all option_id-bearing field values on items that pointed to it.
    # Reconciliation must read-modify-write: read existing options, merge
    # changes into the full list, then write. Never pass a partial list.
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

    def supports_status_overwrite(self) -> bool:
        """Return True iff the target's UpdateProjectV2FieldInput carries
        ``singleSelectOptions``.

        Cloud added it on 2024-12-12 and GHES 3.19+ ships it. The probe is a
        plain GraphQL introspection — works without project scopes — so it can
        front-run the actual mutation and turn an unsupported instance into a
        clear "needs 3.19+" error rather than a 422 during Phase 1.
        """
        data = self.execute(queries.INTROSPECT_UPDATE_FIELD_INPUT)
        type_info = data.get("__type") or {}
        input_fields = type_info.get("inputFields") or []
        return any(f.get("name") == "singleSelectOptions" for f in input_fields)

    # CRITICAL: same replace-the-list semantics as ``create_field``. Whatever
    # ``options`` you pass becomes the new option list verbatim — anything
    # omitted is deleted, and any item value pointing at a deleted option is
    # cleared. Plynth's Phase 1 calls this before any items exist on the
    # project, so nothing is at risk; reconciliation paths must read the
    # existing options and merge before writing.
    def update_field_options(self, field_id: str, options: list[dict]) -> list[dict]:
        """Overwrite the option list on an existing single-select field.

        ``options`` items are ``{"name", "color", "description"}`` dicts in
        the order the operator wants them displayed (the GraphQL mutation
        preserves input order on the system Status field, verified against
        GHES 3.19.4 — see canary in ``.import/single-select-research/``).

        Returns the server's new option list, including freshly-issued
        option IDs. Callers should consume these directly rather than
        re-querying — option IDs rotate on every overwrite.
        """
        data = self.execute(
            mutations.UPDATE_FIELD_OPTIONS,
            {"fieldId": field_id, "options": options},
            is_mutation=True,
        )
        return data["updateProjectV2Field"]["projectV2Field"].get("options", [])

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
