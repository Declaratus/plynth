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


def test_error_hierarchy() -> None:
    # All friendly errors are PlynthError; GraphQLError is also PlynthError now.
    for exc_cls in (AuthError, NotFoundError, NetworkError, GraphQLError):
        assert issubclass(exc_cls, PlynthError)


# ── GraphQL client ──────────────────────────────────────────────


@responses.activate
def test_graphql_401_raises_auth_error() -> None:
    responses.add(responses.POST, GRAPHQL_URL, status=401)
    with pytest.raises(AuthError, match="Token rejected"):
        _gql().get_org_id("nope")


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
    with pytest.raises(AuthError, match="Token rejected"):
        _rest().create_milestone(owner="example-org", repo="acme", title="T")


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
