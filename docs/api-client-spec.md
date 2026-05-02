# API Client Implementation Spec

## What to build

Two API clients and a shared base, then update the phase constants to match the orchestration sequence.

## Files to create

- `plynth/engine/api_base.py` — shared HTTP session, auth, rate limiting, retry logic
- `plynth/engine/graphql_client.py` — GraphQL mutations and queries against GHES
- `plynth/engine/rest_client.py` — REST client (milestone creation only)
- `plynth/queries/__init__.py`
- `plynth/queries/mutations.py` — GraphQL mutation strings
- `plynth/queries/queries.py` — GraphQL query strings

## Design principles

- Single `requests.Session` shared across both clients (one auth header, one connection pool)
- All mutating calls serialize with a configurable delay (default 1 second)
- All calls honor `Retry-After` and `x-ratelimit-reset` headers
- Every mutation returns the parsed response data or raises a clear exception
- No business logic in the clients — they are pure API wrappers. The phase orchestrator (next task) calls them in the right order.

---

## api_base.py — Shared foundation

```python
class GHESClient:
    """Base HTTP client for GHES with rate limiting and retry."""
    
    def __init__(self, ghes_url: str, token: str, write_delay_ms: int = 1000, max_retries: int = 3):
        self.ghes_url = ghes_url  # e.g., "https://ghes.example.com"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })
        self.write_delay_ms = write_delay_ms
        self.max_retries = max_retries
        self._last_write_time: float = 0.0
    
    def _wait_for_write_delay(self):
        """Enforce minimum delay between mutating calls."""
        elapsed = time.time() - self._last_write_time
        remaining = (self.write_delay_ms / 1000.0) - elapsed
        if remaining > 0:
            time.sleep(remaining)
    
    def _record_write(self):
        """Record timestamp after a mutating call."""
        self._last_write_time = time.time()
    
    def _handle_retry(self, response: requests.Response, attempt: int) -> bool:
        """Check if we should retry based on rate limit headers. Returns True if retried."""
        if response.status_code in (429, 403, 502, 503):
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                time.sleep(float(retry_after))
            else:
                # Exponential backoff
                time.sleep(2 ** attempt)
            return True
        return False
```

---

## graphql_client.py

```python
class GraphQLClient:
    """GraphQL client for GHES Projects V2 and Issues API."""
    
    def __init__(self, base: GHESClient):
        self.base = base
        self.endpoint = f"{base.ghes_url}/api/graphql"
    
    def execute(self, query: str, variables: dict | None = None, is_mutation: bool = False) -> dict:
        """Execute a GraphQL query/mutation. Returns the 'data' dict or raises."""
        if is_mutation:
            self.base._wait_for_write_delay()
        
        for attempt in range(self.base.max_retries):
            response = self.base.session.post(
                self.endpoint,
                json={"query": query, "variables": variables or {}},
            )
            
            if response.ok:
                result = response.json()
                if "errors" in result:
                    raise GraphQLError(result["errors"])
                if is_mutation:
                    self.base._record_write()
                return result["data"]
            
            if not self.base._handle_retry(response, attempt):
                response.raise_for_status()
        
        raise RuntimeError(f"Max retries exceeded for GraphQL call")
```

### Methods to implement

Each method calls `self.execute()` with the appropriate query from `queries/mutations.py` or `queries/queries.py` and returns the relevant parsed result.

```python
    # ── Preflight queries ──────────────────────────────────
    
    def get_org_id(self, login: str) -> str:
        """Resolve org login to node ID."""
        # Returns: org node_id string
    
    def get_repo_id(self, owner: str, name: str) -> str:
        """Resolve repo to node ID."""
        # Returns: repo node_id string
    
    # ── Phase 1: Project + Fields ──────────────────────────
    
    def create_project(self, owner_id: str, title: str) -> dict:
        """Create a ProjectV2."""
        # Returns: {"id": "PVT_...", "number": 12, "url": "https://..."}
    
    def create_field(self, project_id: str, name: str, data_type: str, 
                     options: list[dict] | None = None) -> dict:
        """Create a custom field on a project.
        
        data_type: "SINGLE_SELECT", "TEXT", "NUMBER", "DATE", "ITERATION"
        options: for SINGLE_SELECT, list of {"name": "...", "color": "...", "description": ""}
        
        Returns: {"id": "PVTSSF_...", "name": "..."}
        """
    
    def get_project_fields(self, project_id: str) -> list[dict]:
        """Re-query all fields on a project to get field IDs and option IDs.
        
        Returns: list of field dicts, each containing:
          {"id": "...", "name": "...", "dataType": "...", 
           "options": [{"id": "...", "name": "..."}]}  # for single-select
        """
    
    # ── Phase 3: Issue creation ────────────────────────────
    
    def create_issue(self, repository_id: str, title: str, body: str, 
                     milestone_id: str | None = None) -> dict:
        """Create a repository issue via GraphQL.
        
        Note: milestone_id here is the milestone NODE ID, not the number.
        
        Returns: {"id": "I_...", "number": 47, "title": "..."}
        """
    
    # ── Phase 4: Project item management ───────────────────
    
    def add_item_to_project(self, project_id: str, content_id: str) -> str:
        """Add an issue to a project. Returns the project item ID.
        
        Note: if the item already exists on the project, returns the existing item ID.
        
        Returns: item_id string "PVTI_..."
        """
    
    def set_field_value(self, project_id: str, item_id: str, 
                        field_id: str, value: dict) -> None:
        """Set a field value on a project item.
        
        value format depends on field type:
          single_select: {"singleSelectOptionId": "option_id"}
          text: {"text": "value"}
          number: {"number": 123.0}
          date: {"date": "2026-04-01"}
          iteration: {"iterationId": "iter_id"}
        """
    
    # ── Phase 5: Cross-references + dependencies ───────────
    
    def update_issue_body(self, issue_id: str, body: str) -> None:
        """Update an issue's body text (for cross-reference resolution)."""
    
    def add_blocked_by(self, issue_id: str, blocking_issue_id: str) -> None:
        """Create a dependency: issue_id is blocked by blocking_issue_id.
        
        Normalization (handled by caller, not this method):
          template blocked_by: X → add_blocked_by(self_id, X_id)
          template blocks: Y    → add_blocked_by(Y_id, self_id)
        """
```

### GraphQLError exception

```python
class GraphQLError(Exception):
    """Raised when GraphQL response contains errors."""
    def __init__(self, errors: list[dict]):
        self.errors = errors
        messages = [e.get("message", str(e)) for e in errors]
        super().__init__(f"GraphQL errors: {'; '.join(messages)}")
```

---

## rest_client.py

Thin wrapper. Milestone creation is the only REST endpoint needed.

```python
class RESTClient:
    """REST client for GHES operations not available in GraphQL."""
    
    def __init__(self, base: GHESClient):
        self.base = base
    
    def create_milestone(self, owner: str, repo: str, title: str, 
                         description: str = "", due_on: str | None = None) -> dict:
        """Create a repository milestone.
        
        due_on: ISO 8601 date string (e.g., "2026-04-06T00:00:00Z")
        
        Returns: {"number": 3, "node_id": "MI_...", "title": "..."}
        """
        self.base._wait_for_write_delay()
        
        url = f"{self.base.ghes_url}/api/v3/repos/{owner}/{repo}/milestones"
        payload = {"title": title, "description": description}
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
```

---

## queries/mutations.py

All GraphQL mutation strings as module-level constants. Each is a plain string with `$variable` placeholders for the GraphQL variables.

```python
CREATE_PROJECT = """
mutation CreateProject($ownerId: ID!, $title: String!) {
  createProjectV2(input: {ownerId: $ownerId, title: $title}) {
    projectV2 {
      id
      number
      url
    }
  }
}
"""

CREATE_FIELD = """
mutation CreateField($projectId: ID!, $name: String!, $dataType: ProjectV2CustomFieldType!, $options: [ProjectV2SingleSelectFieldOptionInput!]) {
  createProjectV2Field(input: {projectId: $projectId, name: $name, dataType: $dataType, singleSelectOptions: $options}) {
    projectV2Field {
      ... on ProjectV2SingleSelectField {
        id
        name
        options { id name }
      }
      ... on ProjectV2Field {
        id
        name
      }
    }
  }
}
"""

CREATE_ISSUE = """
mutation CreateIssue($repositoryId: ID!, $title: String!, $body: String!, $milestoneId: ID) {
  createIssue(input: {repositoryId: $repositoryId, title: $title, body: $body, milestoneId: $milestoneId}) {
    issue {
      id
      number
      title
    }
  }
}
"""

ADD_ITEM_TO_PROJECT = """
mutation AddItemToProject($projectId: ID!, $contentId: ID!) {
  addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
    item {
      id
    }
  }
}
"""

SET_FIELD_VALUE = """
mutation SetFieldValue($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: ProjectV2FieldValue!) {
  updateProjectV2ItemFieldValue(input: {projectId: $projectId, itemId: $itemId, fieldId: $fieldId, value: $value}) {
    projectV2Item {
      id
    }
  }
}
"""

UPDATE_ISSUE_BODY = """
mutation UpdateIssueBody($issueId: ID!, $body: String!) {
  updateIssue(input: {id: $issueId, body: $body}) {
    issue {
      id
    }
  }
}
"""

ADD_BLOCKED_BY = """
mutation AddBlockedBy($issueId: ID!, $blockingIssueId: ID!) {
  addBlockedBy(input: {issueId: $issueId, blockingIssueId: $blockingIssueId}) {
    issue { id }
    blockingIssue { id }
  }
}
"""
```

---

## queries/queries.py

```python
GET_ORG_ID = """
query GetOrgId($login: String!) {
  organization(login: $login) {
    id
  }
}
"""

GET_REPO_ID = """
query GetRepoId($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    id
  }
}
"""

GET_PROJECT_FIELDS = """
query GetProjectFields($projectId: ID!) {
  node(id: $projectId) {
    ... on ProjectV2 {
      fields(first: 30) {
        nodes {
          ... on ProjectV2SingleSelectField {
            id
            name
            dataType
            options { id name }
          }
          ... on ProjectV2IterationField {
            id
            name
            dataType
            configuration {
              iterations { id title startDate }
            }
          }
          ... on ProjectV2Field {
            id
            name
            dataType
          }
        }
      }
    }
  }
}
"""
```

---

## Testing approach

These clients talk to a real GHES instance, so unit tests should mock `requests.Session`. But for the initial build, just verify:

1. All files import cleanly with no syntax errors
2. `GHESClient` can be instantiated with test values
3. `GraphQLClient` and `RESTClient` can be instantiated from a `GHESClient`
4. All mutation/query strings in `queries/` are valid (no unclosed braces, no Python f-string accidents)
5. Write delay logic works: call `_wait_for_write_delay` twice quickly, verify the second call sleeps

```python
# Quick smoke test
from plynth.engine.api_base import GHESClient
from plynth.engine.graphql_client import GraphQLClient, GraphQLError
from plynth.engine.rest_client import RESTClient
from plynth.queries import mutations, queries

client = GHESClient("https://ghes.example.com", "fake-token", write_delay_ms=100)
gql = GraphQLClient(client)
rest = RESTClient(client)

# Verify all query/mutation constants are strings
for name in dir(mutations):
    if name.isupper():
        val = getattr(mutations, name)
        assert isinstance(val, str), f"{name} is not a string"
        assert "mutation" in val or "query" in val, f"{name} doesn't look like GraphQL"

for name in dir(queries):
    if name.isupper():
        val = getattr(queries, name)
        assert isinstance(val, str), f"{name} is not a string"

print("All API client smoke tests pass.")
```

## Important notes

- The GraphQL endpoint for GHES is `/api/graphql` (not `/graphql`)
- The REST API base for GHES is `/api/v3/` (not bare paths)
- Always use `encoding='utf-8'` for any file I/O
- The `value` parameter in `SET_FIELD_VALUE` uses `ProjectV2FieldValue!` which is a GraphQL input union — the client passes it as a dict that gets serialized to JSON (e.g., `{"singleSelectOptionId": "abc123"}`)
