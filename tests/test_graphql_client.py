from __future__ import annotations

import json

import pytest
import responses

from plynth.engine.api_base import GitHubClient
from plynth.engine.graphql_client import GraphQLClient, GraphQLError

GHES_URL = "https://ghes.example.com"
GRAPHQL_URL = f"{GHES_URL}/api/graphql"


def _client() -> GraphQLClient:
    base = GitHubClient(GHES_URL, "tok", write_delay_ms=0)
    return GraphQLClient(base)


@responses.activate
def test_get_org_id() -> None:
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={"data": {"organization": {"id": "O_kgDO123"}}},
        status=200,
    )
    assert _client().get_org_id("example-org") == "O_kgDO123"


@responses.activate
def test_get_repo_id() -> None:
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={"data": {"repository": {"id": "R_kgDO456"}}},
        status=200,
    )
    assert _client().get_repo_id("example-org", "acme") == "R_kgDO456"


@responses.activate
def test_create_project() -> None:
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={
            "data": {
                "createProjectV2": {
                    "projectV2": {
                        "id": "PVT_1",
                        "number": 7,
                        "url": f"{GHES_URL}/orgs/example-org/projects/7",
                    }
                }
            }
        },
        status=200,
    )
    out = _client().create_project("O_1", "Acme")
    assert out["id"] == "PVT_1"
    assert out["number"] == 7


@responses.activate
def test_create_field_with_options() -> None:
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={
            "data": {
                "createProjectV2Field": {"projectV2Field": {"id": "PVTSSF_1", "name": "Priority"}}
            }
        },
        status=200,
    )
    out = _client().create_field("PVT_1", "Priority", "SINGLE_SELECT", options=[{"name": "P1"}])
    assert out["id"] == "PVTSSF_1"


@responses.activate
def test_get_project_fields() -> None:
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={
            "data": {
                "node": {
                    "fields": {
                        "nodes": [
                            {
                                "id": "PVTSSF_1",
                                "name": "Priority",
                                "options": [{"id": "opt_1", "name": "P1"}],
                            }
                        ]
                    }
                }
            }
        },
        status=200,
    )
    fields = _client().get_project_fields("PVT_1")
    assert fields[0]["name"] == "Priority"
    assert fields[0]["options"][0]["id"] == "opt_1"


@responses.activate
def test_create_issue() -> None:
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={
            "data": {"createIssue": {"issue": {"id": "I_1", "number": 42, "title": "Bootstrap"}}}
        },
        status=200,
    )
    out = _client().create_issue("R_1", "Bootstrap", "body", milestone_id="MI_1")
    assert out["number"] == 42


@responses.activate
def test_add_item_to_project_returns_item_id() -> None:
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={"data": {"addProjectV2ItemById": {"item": {"id": "PVTI_1"}}}},
        status=200,
    )
    assert _client().add_item_to_project("PVT_1", "I_1") == "PVTI_1"


@responses.activate
def test_graphql_error_response_raises() -> None:
    # A generic GraphQL error that isn't classified as NotFoundError still
    # surfaces as GraphQLError — see test_errors.py for the classification cases.
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={"errors": [{"message": "Some other GraphQL failure"}]},
        status=200,
    )
    with pytest.raises(GraphQLError, match="Some other"):
        _client().get_org_id("nope")


# ── #14: configurable Status field ────────────────────────────────


@responses.activate
def test_supports_status_overwrite_true_when_input_field_present() -> None:
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={
            "data": {
                "__type": {
                    "inputFields": [
                        {"name": "fieldId"},
                        {"name": "name"},
                        {"name": "singleSelectOptions"},
                        {"name": "iterationConfiguration"},
                    ]
                }
            }
        },
        status=200,
    )
    assert _client().supports_status_overwrite() is True


@responses.activate
def test_supports_status_overwrite_false_on_pre_3_19_instance() -> None:
    # Older instances expose UpdateProjectV2FieldInput without singleSelectOptions
    # (or even with __type returning null if the input doesn't exist at all).
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={"data": {"__type": {"inputFields": [{"name": "fieldId"}, {"name": "name"}]}}},
        status=200,
    )
    assert _client().supports_status_overwrite() is False


@responses.activate
def test_supports_status_overwrite_false_when_type_missing() -> None:
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={"data": {"__type": None}},
        status=200,
    )
    assert _client().supports_status_overwrite() is False


@responses.activate
def test_update_field_options_returns_server_options() -> None:
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={
            "data": {
                "updateProjectV2Field": {
                    "projectV2Field": {
                        "id": "PVTSSF_1",
                        "name": "Status",
                        "options": [
                            {"id": "abc", "name": "Triaged", "color": "GRAY"},
                            {"id": "def", "name": "Done", "color": "GREEN"},
                        ],
                    }
                }
            }
        },
        status=200,
    )
    out = _client().update_field_options(
        "PVTSSF_1",
        [
            {"name": "Triaged", "color": "GRAY", "description": ""},
            {"name": "Done", "color": "GREEN", "description": ""},
        ],
    )
    assert [o["name"] for o in out] == ["Triaged", "Done"]
    # Server-issued option IDs round-trip back so the caller can wire them
    # into project state without a follow-up re-query.
    assert out[0]["id"] == "abc"


@responses.activate
def test_update_field_options_sends_options_in_input_order() -> None:
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={
            "data": {
                "updateProjectV2Field": {
                    "projectV2Field": {"id": "PVTSSF_1", "name": "Status", "options": []}
                }
            }
        },
        status=200,
    )
    requested = [
        {"name": "Triaged", "color": "GRAY", "description": ""},
        {"name": "Spec'd", "color": "BLUE", "description": ""},
        {"name": "Done", "color": "GREEN", "description": ""},
    ]
    _client().update_field_options("PVTSSF_1", requested)

    sent = responses.calls[0].request
    body_text = sent.body.decode() if isinstance(sent.body, bytes) else sent.body
    payload = json.loads(body_text)
    # Plynth's promise of "order matches template" depends on the request
    # body preserving order — pin it so a future refactor that hands options
    # off to a set/dict-keyed structure trips this test.
    assert [o["name"] for o in payload["variables"]["options"]] == [
        "Triaged",
        "Spec'd",
        "Done",
    ]


@responses.activate
def test_request_body_includes_query_and_variables() -> None:
    responses.add(
        responses.POST,
        GRAPHQL_URL,
        json={"data": {"organization": {"id": "O_1"}}},
        status=200,
    )
    _client().get_org_id("example-org")

    sent = responses.calls[0].request
    assert sent.body is not None
    body_text = sent.body.decode() if isinstance(sent.body, bytes) else sent.body
    payload = json.loads(body_text)

    # Assert query and variables are sent as separate JSON members — not
    # interpolated into the query string. A regression that inlined the login
    # into `query` would fail the variables check below.
    assert "query" in payload
    assert "variables" in payload
    assert payload["variables"] == {"login": "example-org"}
    # The query itself should NOT contain the login literal — it must be a
    # parameterized GraphQL operation.
    assert "example-org" not in payload["query"]
