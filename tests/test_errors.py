"""Tests for the friendly-error mapping in graphql_client and rest_client."""

from __future__ import annotations

import pytest
import requests
import responses

from plynth.engine.api_base import GitHubClient
from plynth.engine.graphql_client import GraphQLClient, GraphQLError
from plynth.engine.rest_client import RESTClient
from plynth.errors import AuthError, NetworkError, NotFoundError, PlynthError

GHES_URL = "https://ghes.example.com"
GRAPHQL_URL = f"{GHES_URL}/api/graphql"
MILESTONE_URL = f"{GHES_URL}/api/v3/repos/example-org/acme/milestones"


def _gql() -> GraphQLClient:
    return GraphQLClient(GitHubClient(GHES_URL, "tok", write_delay_ms=0))


def _rest() -> RESTClient:
    return RESTClient(GitHubClient(GHES_URL, "tok", write_delay_ms=0))


def _assert_token_rejected_wording(msg: str) -> None:
    """Pin the wording produced by ``token_rejected_message`` (#40, PR #58 review).

    All three SECURITY.md-supported token shapes must be named so a user
    with any one of them sees themselves in the advice; ``SECURITY.md``
    must be referenced so a future permission change can update one place.
    """
    assert "Token rejected" in msg
    assert "classic PAT" in msg
    assert "fine-grained PAT" in msg
    assert "GitHub App" in msg
    assert "SECURITY.md" in msg


def _assert_permission_denied_wording(msg: str) -> None:
    """Pin the wording produced by ``permission_denied_message`` (#41).

    Permission-denied 403s must read distinctly from 401 token-rejected — a
    user staring at the message should be able to tell that the token is
    valid but lacks permissions. SECURITY.md must be referenced.
    """
    assert "Permission denied" in msg
    assert "lacks the required permissions" in msg
    assert "SECURITY.md" in msg


def test_error_hierarchy() -> None:
    # All friendly errors are PlynthError; GraphQLError is also PlynthError now.
    for exc_cls in (AuthError, NotFoundError, NetworkError, GraphQLError):
        assert issubclass(exc_cls, PlynthError)


# ── GraphQL client ──────────────────────────────────────────────


@responses.activate
def test_graphql_401_raises_auth_error() -> None:
    responses.add(responses.POST, GRAPHQL_URL, status=401)
    with pytest.raises(AuthError) as excinfo:
        _gql().get_org_id("nope")
    _assert_token_rejected_wording(str(excinfo.value))


@responses.activate
def test_graphql_403_permission_denied_raises_auth_error() -> None:
    """No rate-limit signals: surface AuthError immediately, don't burn retries."""
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        status=403,
        json={"message": "Resource not accessible by integration"},
    )
    with pytest.raises(AuthError) as excinfo:
        _gql().get_org_id("nope")
    _assert_permission_denied_wording(str(excinfo.value))
    # Only one call — no retry loop on a permanent condition.
    assert len(responses.calls) == 1


@responses.activate
def test_graphql_403_labels_query_vs_mutation_correctly() -> None:
    """The 403 message names ``GraphQL query`` on read paths and
    ``GraphQL mutation`` on write paths, so the operation tag in the error
    matches the actual request type."""
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        status=403,
        json={"message": "Resource not accessible by integration"},
    )
    with pytest.raises(AuthError) as excinfo:
        _gql().get_org_id("nope")  # query
    assert "GraphQL query" in str(excinfo.value)
    assert "GraphQL mutation" not in str(excinfo.value)

    responses.reset()
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        status=403,
        json={"message": "Resource not accessible by integration"},
    )
    with pytest.raises(AuthError) as excinfo:
        _gql().create_project(owner_id="O_1", title="T")  # mutation
    assert "GraphQL mutation" in str(excinfo.value)


@responses.activate
def test_permission_denied_message_names_all_three_token_shapes() -> None:
    """Parallel to the 401 token-rejected wording, the 403 advice names
    fine-grained PAT, classic PAT, and GitHub App so a user with any shape
    sees themselves in the advice."""
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        status=403,
        json={"message": "Resource not accessible by integration"},
    )
    with pytest.raises(AuthError) as excinfo:
        _gql().get_org_id("nope")
    msg = str(excinfo.value)
    assert "fine-grained PAT" in msg
    assert "classic PAT" in msg
    assert "GitHub App" in msg


@responses.activate
def test_graphql_403_rate_limited_retries_then_succeeds() -> None:
    """A 403 with a rate-limit signal must retry and succeed on the next try."""
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        status=403,
        headers={"Retry-After": "0"},
        json={"message": "secondary rate limit"},
    )
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        status=200,
        json={"data": {"organization": {"id": "O_1"}}},
    )
    assert _gql().get_org_id("example-org") == "O_1"
    assert len(responses.calls) == 2


@responses.activate
def test_graphql_could_not_resolve_raises_not_found() -> None:
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={
            "errors": [
                {"message": "Could not resolve to an Organization with the login of 'nope'."}
            ]
        },
        status=200,
    )
    with pytest.raises(NotFoundError, match="Could not resolve"):
        _gql().get_org_id("nope")


@responses.activate
def test_graphql_other_error_raises_graphql_error() -> None:
    """Errors that don't match the NotFoundError heuristic still raise GraphQLError."""
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={"errors": [{"message": "Something else went wrong"}]},
        status=200,
    )
    with pytest.raises(GraphQLError, match="Something else"):
        _gql().get_org_id("nope")


@responses.activate
def test_graphql_timeout_raises_network_error() -> None:
    def _timeout(_req: object) -> None:
        raise requests.Timeout("simulated timeout")

    responses.add_callback(responses.POST, GRAPHQL_URL, callback=_timeout)
    with pytest.raises(NetworkError, match="timed out after 30s"):
        _gql().get_org_id("nope")


@responses.activate
def test_graphql_connection_error_raises_network_error() -> None:
    def _conn_err(_req: object) -> None:
        raise requests.ConnectionError("name resolution failed")

    responses.add_callback(responses.POST, GRAPHQL_URL, callback=_conn_err)
    with pytest.raises(NetworkError, match="Could not connect"):
        _gql().get_org_id("nope")


def test_graphql_timeout_kwarg_passed_to_session_post() -> None:
    """The client's `request_timeout_s` must be forwarded to session.post as
    the `timeout=` kwarg — not just embedded in error messages. Patch
    session.post to capture the kwargs and assert the value directly."""
    from unittest.mock import MagicMock, patch

    base = GitHubClient(GHES_URL, "tok", write_delay_ms=0, request_timeout_s=7)
    gql = GraphQLClient(base)

    fake_response = MagicMock()
    fake_response.ok = True
    fake_response.json.return_value = {"data": {"organization": {"id": "O_1"}}}

    with patch.object(base.session, "post", return_value=fake_response) as mock_post:
        gql.get_org_id("example-org")

    mock_post.assert_called_once()
    assert mock_post.call_args.kwargs["timeout"] == 7


def test_graphql_timeout_message_uses_configured_value() -> None:
    """A timeout error surfaces with the client's configured timeout in the message."""
    base = GitHubClient(GHES_URL, "tok", write_delay_ms=0, request_timeout_s=7)
    gql = GraphQLClient(base)

    @responses.activate
    def _do() -> None:
        def _timeout(_req: object) -> None:
            raise requests.Timeout()

        responses.add_callback(responses.POST, GRAPHQL_URL, callback=_timeout)
        with pytest.raises(NetworkError, match="timed out after 7s"):
            gql.get_org_id("nope")

    _do()


# ── REST client ────────────────────────────────────────────────


@responses.activate
def test_rest_401_raises_auth_error() -> None:
    responses.add(responses.POST, MILESTONE_URL, status=401)
    with pytest.raises(AuthError) as excinfo:
        _rest().create_milestone(owner="example-org", repo="acme", title="T")
    # REST and GraphQL share the same helper, so they MUST produce the
    # same wording — pin both with the shared assertion.
    _assert_token_rejected_wording(str(excinfo.value))


@responses.activate
def test_rest_milestone_403_permission_denied_raises_auth_error() -> None:
    """Repro of the bug in #41: a permission-denied 403 surfaces as AuthError
    pointing at SECURITY.md, not as 'Max retries exceeded'."""
    responses.add(
        responses.POST,
        MILESTONE_URL,
        status=403,
        json={"message": "Resource not accessible by integration"},
    )
    with pytest.raises(AuthError) as excinfo:
        _rest().create_milestone(owner="example-org", repo="acme", title="Acme Foundation")
    msg = str(excinfo.value)
    _assert_permission_denied_wording(msg)
    # The operation name is folded into the message so a user with multiple
    # phases failing can map back to the call site.
    assert "Acme Foundation" in msg
    assert len(responses.calls) == 1


@responses.activate
def test_rest_milestone_403_rate_limited_retries_then_succeeds() -> None:
    responses.add(
        responses.POST,
        MILESTONE_URL,
        status=403,
        headers={"Retry-After": "0"},
        json={"message": "You have exceeded a secondary rate limit."},
    )
    responses.add(
        responses.POST,
        MILESTONE_URL,
        status=201,
        json={"number": 3, "node_id": "MI_1", "title": "T"},
    )
    result = _rest().create_milestone(owner="example-org", repo="acme", title="T")
    assert result == {"number": 3, "node_id": "MI_1", "title": "T"}
    assert len(responses.calls) == 2


@responses.activate
def test_rest_create_repo_403_permission_denied_raises_auth_error() -> None:
    """create_repo keeps its operation-specific Administration wording."""
    repo_url = f"{GHES_URL}/api/v3/orgs/example-org/repos"
    responses.add(
        responses.POST,
        repo_url,
        status=403,
        json={"message": "Resource not accessible by integration"},
    )
    with pytest.raises(AuthError) as excinfo:
        _rest().create_repo(org="example-org", name="acme")
    msg = str(excinfo.value)
    assert "Permission denied" in msg
    assert "Administration: Read and write" in msg
    assert "SECURITY.md" in msg
    assert len(responses.calls) == 1


@responses.activate
def test_rest_404_raises_not_found_error() -> None:
    responses.add(responses.POST, MILESTONE_URL, status=404, json={"message": "Not Found"})
    with pytest.raises(NotFoundError, match="example-org/acme not found"):
        _rest().create_milestone(owner="example-org", repo="acme", title="T")


@responses.activate
def test_rest_timeout_raises_network_error() -> None:
    def _timeout(_req: object) -> None:
        raise requests.Timeout("simulated")

    responses.add_callback(responses.POST, MILESTONE_URL, callback=_timeout)
    with pytest.raises(NetworkError, match="timed out after 30s"):
        _rest().create_milestone(owner="example-org", repo="acme", title="T")


@responses.activate
def test_rest_connection_error_raises_network_error() -> None:
    def _conn_err(_req: object) -> None:
        raise requests.ConnectionError("connection refused")

    responses.add_callback(responses.POST, MILESTONE_URL, callback=_conn_err)
    with pytest.raises(NetworkError, match="Could not connect"):
        _rest().create_milestone(owner="example-org", repo="acme", title="T")


# ── CLI top-level handler ──────────────────────────────────────


def test_cli_main_exits_2_on_plynth_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: object,  # pytest's tmp_path
) -> None:
    """A PlynthError raised during dry-run should produce `Error: ...` + exit code 2."""
    from plynth import cli

    # Point at a non-existent template — _load_template raises ConfigError.
    monkeypatch.setattr(
        "sys.argv",
        [
            "plynth",
            "create",
            "--template",
            "/does/not/exist.yaml",
            "--instance",
            "/does/not/exist.yaml",
            "--dry-run",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "Error: Template file not found" in captured.err


def test_cli_main_rejects_format_json_without_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--format json` without `--dry-run` is a usage error, not a silent no-op."""
    from plynth import cli

    monkeypatch.setattr(
        "sys.argv",
        [
            "plynth",
            "create",
            "--template",
            "tests/fixtures/minimal-template.yaml",
            "--instance",
            "tests/fixtures/minimal-instance.yaml",
            "--format",
            "json",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    # parser.error exits with code 2 and writes to stderr.
    assert exc_info.value.code == 2
    assert "--format only applies to --dry-run" in capsys.readouterr().err
