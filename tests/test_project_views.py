"""GHEC view contracts, preflight and persisted resume behavior."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
import responses
import yaml

from plynth.engine.api_base import GitHubClient
from plynth.engine.graphql_client import GraphQLClient
from plynth.engine.phases import PhaseOrchestrator
from plynth.engine.planner import api_call_estimate, format_dry_run, plan
from plynth.engine.rest_client import RESTClient
from plynth.errors import AuthError, ConfigError, NetworkError, NotFoundError, PlynthError
from plynth.models.instance import InstanceConfig
from plynth.models.state import ProjectState, StateFile
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
    with pytest.raises(ConfigError, match="GHEC"):
        plan(template, minimal_instance)
    instance = minimal_instance.model_copy(update={"target": "github.com"})
    ep = plan(template, instance)
    assert ep.views[0].name == "Acme Intake"
    assert api_call_estimate(ep)["views_create"] == 1
    assert "Acme Intake [table]: create via REST" in format_dry_run(ep)
    assert "Manual [board]: documentation only" in format_dry_run(ep)
    template.views.append(template.views[0])
    with pytest.raises(ConfigError, match="unique resolved names"):
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
    with (
        patch.object(GraphQLClient, "get_project_views", return_value=[]),
        pytest.raises(AuthError),
    ):
        orchestrator(state).phase_6_create_views()
    saved = StateFile.model_validate(yaml.safe_load(state_path.read_text()))
    assert set(saved.views) == {"Intake"}
    responses.post(VIEW_URL, json=_response(3), status=201)
    with patch.object(GraphQLClient, "get_project_views", return_value=[]):
        orchestrator(saved).phase_6_create_views()
    assert set(saved.views) == {"Intake", "Delivery"}
    assert [json.loads(call.request.body)["name"] for call in responses.calls] == [
        "Intake",
        "Delivery",
        "Delivery",
    ]
    # Old state files remain readable with an empty view mapping.
    assert StateFile.model_validate({"schema_version": "1.0"}).views == {}


@responses.activate
@pytest.mark.parametrize("wrapped", [True, False])
@pytest.mark.parametrize("status", [200, 201, 202])
def test_success_response_shapes(wrapped: bool, status: int) -> None:
    data = _response(2)
    responses.post(VIEW_URL, json=data if wrapped else data["value"], status=status)
    result = RESTClient(GitHubClient("github.com", "test", write_delay_ms=0)).create_project_view(
        "example-org", 7, "Intake", "table"
    )
    assert result["number"] == 2


@responses.activate
@pytest.mark.parametrize("body", [{"value": {}}, {}, [], {"value": {"number": "2"}}])
def test_malformed_success_is_uncertain_and_not_replayed(body: object) -> None:
    responses.post(VIEW_URL, json=body, status=201)
    with pytest.raises(NetworkError, match="unconfirmed response"):
        RESTClient(GitHubClient("github.com", "test", write_delay_ms=0)).create_project_view(
            "example-org", 7, "Intake", "table"
        )
    assert len(responses.calls) == 1


@responses.activate
def test_422_is_a_user_facing_error() -> None:
    responses.post(VIEW_URL, json={"message": "Validation failed"}, status=422)
    with pytest.raises(ConfigError, match="422"):
        RESTClient(GitHubClient("github.com", "test", write_delay_ms=0)).create_project_view(
            "example-org", 7, "Intake", "table"
        )
    assert len(responses.calls) == 1


def test_manual_views_preserve_placeholders_and_warn(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    view = ViewDefinition(name="{APP} literal {UNKNOWN}", layout="table", filter_query="{APP}")
    minimal_template.views = [view]
    ep = plan(minimal_template, minimal_instance)
    assert ep.views[0] == view
    assert "not applied" in ep.warnings[-1]
    assert "filter (documentation; not applied)" in format_dry_run(ep)


def test_resolved_blank_name_is_a_config_error(
    minimal_template: TemplateDefinition, minimal_instance: InstanceConfig
) -> None:
    minimal_template.views = [ViewDefinition(name="{EMPTY}", layout="table", create=True)]
    minimal_instance.target = "github.com"
    minimal_instance.values["EMPTY"] = " "
    with pytest.raises(ConfigError, match="Invalid resolved view"):
        plan(minimal_template, minimal_instance)


def test_shipped_zero_issue_example_loads_and_plans() -> None:
    root = Path(__file__).resolve().parents[1] / "docs/examples"
    template = TemplateDefinition.model_validate(
        yaml.safe_load((root / "ghec-portfolio-template.yaml").read_text())
    )
    instance = InstanceConfig.model_validate(
        yaml.safe_load((root / "declaratus-portfolio-instance.yaml").read_text())
    )
    ep = plan(template, instance)
    assert not ep.issues and not ep.milestones
    assert api_call_estimate(ep)["views_create"] == 4


def test_state_version_and_legacy_empty_shape() -> None:
    old = StateFile().model_dump()
    assert old["schema_version"] == "1.0"
    assert "views" not in old and "pending_views" not in old
    state = StateFile(pending_views=["Intake"])
    assert state.model_dump()["schema_version"] == "1.1"
    assert StateFile.model_validate(state.model_dump()).pending_views == ["Intake"]


def _view_orchestrator(template, instance, tmp_path):
    template.views = [ViewDefinition(name="Intake", layout="table", create=True)]
    instance.target = "github.com"
    base = GitHubClient("github.com", "test", write_delay_ms=0)
    return PhaseOrchestrator(
        plan(template, instance),
        GraphQLClient(base),
        RESTClient(base),
        StateFile(project=ProjectState(node_id="PVT_7", number=7)),
        tmp_path / "state.yaml",
    )


def _remote_view() -> dict:
    return {"id": "PVTV_2", "number": 2, "name": "Intake", "layout": "TABLE_LAYOUT", "filter": ""}


@responses.activate
def test_success_then_checkpoint_failure_recovers_without_duplicate(
    minimal_template, minimal_instance, tmp_path
) -> None:
    orch = _view_orchestrator(minimal_template, minimal_instance, tmp_path)
    responses.post(VIEW_URL, json=_response(2), status=201)
    save = orch._save_state

    def checkpoint():
        if orch.state.views:
            raise OSError("disk write failed")
        save()

    with (
        patch.object(orch.gql, "get_project_views", return_value=[]),
        patch.object(orch, "_save_state", side_effect=checkpoint),
        pytest.raises(OSError),
    ):
        orch.phase_6_create_views()
    loaded = StateFile.model_validate(yaml.safe_load(orch.state_path.read_text()))
    assert loaded.pending_views == ["Intake"] and not loaded.views
    orch.state = loaded
    with patch.object(orch.gql, "get_project_views", return_value=[_remote_view()]):
        orch.phase_6_create_views()
    assert len(responses.calls) == 1
    assert orch.state.views["Intake"].node_id == "PVTV_2"
    assert not orch.state.pending_views


@responses.activate
def test_pending_absent_view_never_replays_post(
    minimal_template, minimal_instance, tmp_path
) -> None:
    orch = _view_orchestrator(minimal_template, minimal_instance, tmp_path)
    orch.state.pending_views = ["Intake"]
    with (
        patch.object(orch.gql, "get_project_views", return_value=[]) as read,
        patch("plynth.engine.phases.time.sleep"),
        pytest.raises(PlynthError, match="No POST was replayed"),
    ):
        orch.phase_6_create_views()
    assert read.call_count == 3
    assert not responses.calls


@responses.activate
def test_pending_creation_recovers_after_delayed_read(minimal_template, minimal_instance, tmp_path):
    orch = _view_orchestrator(minimal_template, minimal_instance, tmp_path)
    orch.state.pending_views = ["Intake"]
    with (
        patch.object(orch.gql, "get_project_views", side_effect=[[], [_remote_view()]]) as read,
        patch("plynth.engine.phases.time.sleep"),
    ):
        orch.phase_6_create_views()
    assert read.call_count == 2
    assert orch.state.views["Intake"].number == 2
    assert not responses.calls


@responses.activate
def test_uncertain_creation_preserves_pending_checkpoint(
    minimal_template, minimal_instance, tmp_path
):
    orch = _view_orchestrator(minimal_template, minimal_instance, tmp_path)
    responses.post(VIEW_URL, body=requests.Timeout("timeout"))
    with patch.object(orch.gql, "get_project_views", return_value=[]), pytest.raises(NetworkError):
        orch.phase_6_create_views()
    saved = StateFile.model_validate(yaml.safe_load(orch.state_path.read_text()))
    assert saved.pending_views == ["Intake"] and not saved.views
    orch.state = saved
    with patch.object(orch.gql, "get_project_views", return_value=[_remote_view()]):
        orch.phase_6_create_views()
    assert len(responses.calls) == 1


@responses.activate
@pytest.mark.parametrize("duplicate", [True, False])
def test_remote_name_conflicts_refuse_creation(
    minimal_template, minimal_instance, tmp_path, duplicate
) -> None:
    orch = _view_orchestrator(minimal_template, minimal_instance, tmp_path)
    remote = (
        [_remote_view(), _remote_view()]
        if duplicate
        else [{**_remote_view(), "filter": "is:closed"}]
    )
    with (
        patch.object(orch.gql, "get_project_views", return_value=remote),
        pytest.raises(ConfigError, match="ambiguous or differs"),
    ):
        orch.phase_6_create_views()
    assert not responses.calls


@responses.activate
def test_view_read_pagination() -> None:
    url = "https://api.github.com/graphql"
    for more, nodes, cursor in [(True, [], "page2"), (False, [_remote_view()], None)]:
        responses.post(
            url,
            json={
                "data": {
                    "node": {
                        "views": {
                            "nodes": nodes,
                            "pageInfo": {"hasNextPage": more, "endCursor": cursor},
                        }
                    }
                }
            },
        )
    client = GraphQLClient(GitHubClient("github.com", "test", write_delay_ms=0))
    assert client.get_project_views("PVT_7") == [_remote_view()]
    assert json.loads(responses.calls[1].request.body)["variables"]["after"] == "page2"


@responses.activate
def test_view_read_invalid_cursor_refuses_truncated_result() -> None:
    responses.post(
        "https://api.github.com/graphql",
        json={
            "data": {
                "node": {
                    "views": {
                        "nodes": [_remote_view()],
                        "pageInfo": {"hasNextPage": True, "endCursor": None},
                    }
                }
            }
        },
    )
    client = GraphQLClient(GitHubClient("github.com", "test", write_delay_ms=0))
    with pytest.raises(PlynthError, match="complete Project views"):
        client.get_project_views("PVT_7")


def test_failed_atomic_replace_preserves_checkpoint(minimal_template, minimal_instance, tmp_path):
    orch = _view_orchestrator(minimal_template, minimal_instance, tmp_path)
    orch._save_state()
    previous = orch.state_path.read_text()
    orch.state.pending_views = ["Intake"]
    with patch.object(Path, "replace", side_effect=OSError("disk error")), pytest.raises(OSError):
        orch._save_state()
    assert orch.state_path.read_text() == previous
    assert list(tmp_path.iterdir()) == [orch.state_path]


@responses.activate
@pytest.mark.parametrize("client", ["gql", "rest"])
def test_execute_checks_actual_clients_before_side_effects(
    minimal_template, minimal_instance, tmp_path, client
):
    orch = _view_orchestrator(minimal_template, minimal_instance, tmp_path)
    base = GitHubClient("https://ghes.example.com", "test", write_delay_ms=0)
    if client == "gql":
        orch.gql = GraphQLClient(base)
    else:
        orch.rest = RESTClient(base)
    with pytest.raises(ConfigError, match="GHEC"):
        orch.execute()
    assert not responses.calls
    assert not orch.state.phases
