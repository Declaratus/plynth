from __future__ import annotations

import json

import pytest
import requests
import responses

from plynth.engine.api_base import GitHubClient
from plynth.engine.rest_client import RESTClient

GHES_URL = "https://ghes.example.com"
MILESTONE_URL = f"{GHES_URL}/api/v3/repos/example-org/acme/milestones"


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
