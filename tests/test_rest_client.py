from __future__ import annotations

import json
import logging

import pytest
import requests
import responses

from plynth.engine.api_base import GitHubClient
from plynth.engine.rest_client import RESTClient, _parse_version
from plynth.errors import AuthError, NotFoundError

GHES_URL = "https://ghes.example.com"
MILESTONE_URL = f"{GHES_URL}/api/v3/repos/example-org/acme/milestones"
ORG_REPOS_URL = f"{GHES_URL}/api/v3/orgs/example-org/repos"
META_URL = f"{GHES_URL}/api/v3/meta"


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


# ── /meta version detection ───────────────────────────────────


@responses.activate
def test_detect_installed_version_ghes_happy_path(caplog: pytest.LogCaptureFixture) -> None:
    responses.add(
        responses.GET,
        META_URL,
        json={"installed_version": "3.20.1", "verifiable_password_authentication": False},
        status=200,
    )
    client = _client()
    log = logging.getLogger("plynth.test.detect_happy")
    with caplog.at_level(logging.INFO, logger=log.name):
        client.detect_installed_version(log)

    assert client.base.installed_version == (3, 20)
    msgs = [r.message for r in caplog.records if r.name == log.name]
    assert any("Detected GHES 3.20" in m for m in msgs)


def test_detect_installed_version_github_com_skips() -> None:
    """github.com targets must not call /meta and must leave installed_version None."""
    base = GitHubClient("github.com", "tok", write_delay_ms=0)
    rest = RESTClient(base)

    @responses.activate
    def _run() -> None:
        # If detect_installed_version did issue a request, `responses` would
        # raise ConnectionError because no mock is registered.
        rest.detect_installed_version(logging.getLogger("plynth.test.detect_dotcom"))

    _run()
    assert base.installed_version is None


@responses.activate
def test_detect_installed_version_404_logs_and_leaves_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    responses.add(responses.GET, META_URL, json={"message": "Not Found"}, status=404)
    client = _client()
    log = logging.getLogger("plynth.test.detect_404")
    with caplog.at_level(logging.WARNING, logger=log.name):
        client.detect_installed_version(log)

    assert client.base.installed_version is None
    msgs = [r.message for r in caplog.records if r.name == log.name]
    assert any("HTTP 404" in m for m in msgs)


@responses.activate
def test_detect_installed_version_missing_field_logs_and_leaves_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    responses.add(responses.GET, META_URL, json={"ssh_key_fingerprints": {}}, status=200)
    client = _client()
    log = logging.getLogger("plynth.test.detect_missing_field")
    with caplog.at_level(logging.WARNING, logger=log.name):
        client.detect_installed_version(log)

    assert client.base.installed_version is None
    msgs = [r.message for r in caplog.records if r.name == log.name]
    assert any("missing or malformed installed_version" in m for m in msgs)


@responses.activate
def test_detect_installed_version_timeout_logs_and_leaves_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    responses.add(responses.GET, META_URL, body=requests.Timeout("read timeout"))
    client = _client()
    log = logging.getLogger("plynth.test.detect_timeout")
    with caplog.at_level(logging.WARNING, logger=log.name):
        client.detect_installed_version(log)

    assert client.base.installed_version is None
    msgs = [r.message for r in caplog.records if r.name == log.name]
    assert any("Could not reach" in m for m in msgs)


def test_detect_installed_version_silent_without_logger() -> None:
    """Calling without a logger must not raise; the caller may not have one yet."""
    base = GitHubClient("github.com", "tok", write_delay_ms=0)
    RESTClient(base).detect_installed_version()
    assert base.installed_version is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("3.20.1", (3, 20)),
        ("3.20", (3, 20)),
        ("3.20.1-rc1", (3, 20)),  # patch ignored, prerelease tolerated
        ("4.0.0", (4, 0)),
        ("3", None),
        ("", None),
        ("not-a-version", None),
        (None, None),
        (320, None),  # non-string
    ],
)
def test_parse_version(raw: object, expected: tuple[int, int] | None) -> None:
    assert _parse_version(raw) == expected
