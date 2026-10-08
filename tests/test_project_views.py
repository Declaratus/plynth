"""GHEC view contracts, preflight and persisted resume behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
import responses
import yaml

from plynth.engine.api_base import GitHubClient
from plynth.engine.graphql_client import GraphQLClient
from plynth.engine.phases import PhaseOrchestrator
from plynth.engine.planner import api_call_estimate, format_dry_run, plan
from plynth.engine.rest_client import RESTClient
from plynth.errors import AuthError, NetworkError, NotFoundError, PlynthError
from plynth.models.instance import InstanceConfig
from plynth.models.state import PHASE_6_VIEWS, ProjectState, StateFile
from plynth.models.template import TemplateDefinition, ViewDefinition

VIEW_URL = "https://api.github.com/orgs/example-org/projectsV2/7/views"


def _response(number: int) -> dict:
    return {
        "value": {
            "node_id": f"PVTV_{number}",
            "number": number,
            "html_url": f"https://github.com/orgs/example-org/projects/7/views/{number}",
        }
    }


@responses.activate
@pytest.mark.parametrize("layout", ["table", "board", "roadmap"])
def test_rest_view_contract(layout: str) -> None:
    responses.post(VIEW_URL, json=_response(2), status=201)
    base = GitHubClient("github.com", "test-token", write_delay_ms=0)
    result = RESTClient(base).create_project_view(
        "example-org", 7, "Intake", layout, 'is:open Status:"Todo"'
    )
    assert result["node_id"] == "PVTV_2"
    request = responses.calls[0].request
    assert json.loads(request.body) == {
        "name": "Intake",
        "layout": layout,
        "filter": 'is:open Status:"Todo"',
    }
    assert request.headers["X-GitHub-Api-Version"] == "2026-03-10"
    # The newer version belongs only to the view endpoint.
    assert base.session.headers["X-GitHub-Api-Version"] == "2022-11-28"


@responses.activate
@pytest.mark.parametrize(
    ("status", "error"), [(401, AuthError), (403, AuthError), (404, NotFoundError)]
)
def test_rest_access_failures_are_not_retried(status: int, error: type[Exception]) -> None:
    responses.post(VIEW_URL, json={"message": "Denied"}, status=status)
    client = RESTClient(GitHubClient("github.com", "test-token", write_delay_ms=0))
    with pytest.raises(error):
        client.create_project_view("example-org", 7, "Intake", "table")
    assert len(responses.calls) == 1


@responses.activate
@pytest.mark.parametrize("failure", [500, requests.Timeout("timeout")])
def test_ambiguous_post_failure_is_not_replayed(failure: object) -> None:
    if isinstance(failure, int):
        responses.post(VIEW_URL, status=failure)
    else:
        responses.post(VIEW_URL, body=failure)
    client = RESTClient(GitHubClient("github.com", "test-token", write_delay_ms=0))
    with pytest.raises(NetworkError, match="inspect the project"):
        client.create_project_view("example-org", 7, "Intake", "table")
    assert len(responses.calls) == 1


@responses.activate
def test_ghes_rest_guard_issues_no_requests() -> None:
    client = RESTClient(GitHubClient("https://ghes.example.com", "test-token"))
    with pytest.raises(PlynthError, match="GHEC"):
        client.create_project_view("example-org", 7, "Intake", "table")
    assert len(responses.calls) == 0


def test_view_preflight_and_dry_run(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    template = minimal_template.model_copy(
        update={
            "views": [
                ViewDefinition(
                    name="{APP} Intake", layout="table", create=True, filter_query="is:open"
                ),
                ViewDefinition(name="Manual", layout="board", group_by="Status"),
            ]
        }
    )
    with pytest.raises(ValueError, match="GHEC"):
        plan(template, minimal_instance)
    instance = minimal_instance.model_copy(update={"target": "github.com"})
    ep = plan(template, instance)
    assert ep.views[0].name == "Acme Intake"
    assert api_call_estimate(ep)["views_create"] == 1
    assert "Acme Intake [table]: create via REST" in format_dry_run(ep)
    assert "Manual [board]: documentation only" in format_dry_run(ep)
    template.views.append(template.views[0])
    with pytest.raises(ValueError, match="unique resolved names"):
        plan(template, instance)


def test_created_views_reject_unimplemented_settings() -> None:
    with pytest.raises(ValueError, match="configure group_by in the UI"):
        ViewDefinition(name="Intake", layout="board", create=True, group_by="Status")
    with pytest.raises(ValueError, match="non-empty name"):
        ViewDefinition(name=" ", layout="table", create=True)


@responses.activate
def test_partial_view_creation_resumes_from_checkpoint(
    minimal_template: TemplateDefinition,
    minimal_instance: InstanceConfig,
    tmp_path: Path,
) -> None:
    template = minimal_template.model_copy(
        update={
            "views": [
                ViewDefinition(name="Intake", layout="table", create=True),
                ViewDefinition(name="Delivery", layout="board", create=True),
            ]
        }
    )
    instance = minimal_instance.model_copy(update={"target": "github.com"})
    ep = plan(template, instance)
    state = StateFile(project=ProjectState(node_id="PVT_7", number=7))
    state_path = tmp_path / "state.yaml"
    base = GitHubClient("github.com", "test-token", write_delay_ms=0)

    def orchestrator(saved: StateFile) -> PhaseOrchestrator:
        return PhaseOrchestrator(ep, GraphQLClient(base), RESTClient(base), saved, state_path)

    responses.post(VIEW_URL, json=_response(2), status=201)
    responses.post(VIEW_URL, json={"message": "Forbidden"}, status=403)
    with pytest.raises(AuthError):
        orchestrator(state).phase_6_create_views()
    saved = StateFile.model_validate(yaml.safe_load(state_path.read_text()))
    assert set(saved.views) == {"Intake"}
    responses.post(VIEW_URL, json=_response(3), status=201)
    orchestrator(saved).phase_6_create_views()
    assert set(saved.views) == {"Intake", "Delivery"}
    assert [json.loads(call.request.body)["name"] for call in responses.calls] == [
        "Intake",
        "Delivery",
        "Delivery",
    ]
    saved.mark_phase_complete(PHASE_6_VIEWS)
    # Old state files remain readable with an empty view mapping.
    assert StateFile.model_validate({"schema_version": "1.0"}).views == {}
