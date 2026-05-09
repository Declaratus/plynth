from __future__ import annotations

import json

import pytest
import requests
import responses

from plynth.engine.api_base import GitHubClient
from plynth.engine.rest_client import RESTClient
from plynth.errors import AuthError, NotFoundError

GHES_URL = "https://ghes.example.com"
MILESTONE_URL = f"{GHES_URL}/api/v3/repos/example-org/acme/milestones"
ORG_REPOS_URL = f"{GHES_URL}/api/v3/orgs/example-org/repos"


def _client() -> RESTClient:
    base = GitHubClient(GHES_URL, "tok", write_delay_ms=0)
    return RESTClient(base)


@responses.activate
def test_create_milestone_happy_path() -> None:
    responses.add(
        responses.POST,
        MILESTONE_URL,
        json={"number": 3, "node_id": "MI_1", "title": "Foundation"},
        status=201,
    )
    result = _client().create_milestone(
        owner="example-org",
        repo="acme",
        title="Foundation",
        description="d",
        due_on="2026-05-15T00:00:00Z",
    )
    assert result == {"number": 3, "node_id": "MI_1", "title": "Foundation"}

    sent_body = json.loads(responses.calls[0].request.body)
    assert sent_body["title"] == "Foundation"
    assert sent_body["due_on"] == "2026-05-15T00:00:00Z"


@responses.activate
def test_create_milestone_omits_due_on_if_none() -> None:
    responses.add(
        responses.POST,
        MILESTONE_URL,
        json={"number": 1, "node_id": "MI_2", "title": "T"},
        status=201,
    )
    _client().create_milestone(owner="example-org", repo="acme", title="T")
    sent_body = json.loads(responses.calls[0].request.body)
    assert "due_on" not in sent_body


@responses.activate
def test_create_milestone_422_raises() -> None:
    responses.add(
        responses.POST,
        MILESTONE_URL,
        json={"message": "Validation failed"},
        status=422,
    )
    with pytest.raises(requests.HTTPError):
        _client().create_milestone(owner="example-org", repo="acme", title="T")


@responses.activate
def test_create_repo_happy_path() -> None:
    responses.add(
        responses.POST,
        ORG_REPOS_URL,
        json={"node_id": "R_kgDO123", "name": "acme"},
        status=201,
    )
    result = _client().create_repo(org="example-org", name="acme")
    assert result == {"node_id": "R_kgDO123", "name": "acme"}

    sent_body = json.loads(responses.calls[0].request.body)
    assert sent_body == {"name": "acme", "private": True}


@responses.activate
def test_create_repo_401_raises_auth_error() -> None:
    responses.add(
        responses.POST,
        ORG_REPOS_URL,
        json={"message": "Bad credentials"},
        status=401,
    )
    with pytest.raises(AuthError, match="creating a repo requires"):
        _client().create_repo(org="example-org", name="acme")


@responses.activate
def test_create_repo_404_raises_not_found() -> None:
    responses.add(
        responses.POST,
        ORG_REPOS_URL,
        json={"message": "Not Found"},
        status=404,
    )
    with pytest.raises(NotFoundError, match="Organization example-org not found"):
        _client().create_repo(org="example-org", name="acme")


@responses.activate
def test_create_repo_422_raises() -> None:
    """Name collision (repo already exists) surfaces as HTTPError. The Phase 1
    flow avoids this case by checking existence with get_repo_id first; this
    test pins the contract for any direct caller."""
    responses.add(
        responses.POST,
        ORG_REPOS_URL,
        json={"message": "name already exists on this account"},
        status=422,
    )
    with pytest.raises(requests.HTTPError):
        _client().create_repo(org="example-org", name="acme")
