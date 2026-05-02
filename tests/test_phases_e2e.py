"""End-to-end orchestrator test against a mocked GHES server.

Exercises Phases 1→5 + 7 against a single in-test GraphQL dispatcher and a
sequenced REST mock. Asserts the resulting state file contents and that a
second run of `execute()` is a no-op (resume behavior).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import responses
import yaml

from plynth.engine.api_base import GitHubClient
from plynth.engine.graphql_client import GraphQLClient
from plynth.engine.phases import PhaseOrchestrator
from plynth.engine.planner import plan
from plynth.engine.rest_client import RESTClient
from plynth.models.instance import InstanceConfig
from plynth.models.state import (
    PHASE_1_PROJECT_AND_FIELDS,
    PHASE_2_MILESTONES,
    PHASE_3_ISSUES,
    PHASE_4_PROJECT_ITEMS,
    PHASE_5_REFERENCES_AND_DEPS,
    PHASE_7_STATE_FILE,
    StateFile,
)
from plynth.models.template import TemplateDefinition

GHES_URL = "https://ghes.example.com"
GRAPHQL_URL = f"{GHES_URL}/api/graphql"


class _GraphQLDispatcher:
    """Dispatches GraphQL POSTs by inspecting the query body.

    The plynth GraphQL client uses a single endpoint, so `responses` cannot
    distinguish operations by URL alone — we route on substrings of the query
    body and produce real issue numbers in the order they were created.
    """

    def __init__(self) -> None:
        self.next_issue_number = 47  # non-sequential / non-1-based on purpose
        self.next_item_id = 1
        self.created_issue_node_ids: list[str] = []
        self.body_updates: list[tuple[str, str]] = []
        self.add_blocked_by_calls: list[tuple[str, str]] = []

    def __call__(self, request) -> tuple[int, dict, str]:  # type: ignore[no-untyped-def]
        payload = json.loads(request.body)
        query = payload["query"]
        variables = payload.get("variables", {})

        if "GET_ORG_ID" in query or "organization(login" in query:
            return (200, {}, json.dumps({"data": {"organization": {"id": "O_1"}}}))

        if "repository(owner" in query and "name" in query:
            return (200, {}, json.dumps({"data": {"repository": {"id": "R_1"}}}))

        if "createProjectV2(" in query:
            return (
                200,
                {},
                json.dumps(
                    {
                        "data": {
                            "createProjectV2": {
                                "projectV2": {
                                    "id": "PVT_1",
                                    "number": 7,
                                    "url": f"{GHES_URL}/orgs/example-org/projects/7",
                                }
                            }
                        }
                    }
                ),
            )

        if "createProjectV2Field(" in query:
            return (
                200,
                {},
                json.dumps(
                    {
                        "data": {
                            "createProjectV2Field": {
                                "projectV2Field": {
                                    "id": f"PVTSSF_{variables['name']}",
                                    "name": variables["name"],
                                }
                            }
                        }
                    }
                ),
            )

        if "node(id:" in query and "ProjectV2" in query:
            # get_project_fields — return Status (built-in) plus our custom fields.
            return (
                200,
                {},
                json.dumps(
                    {
                        "data": {
                            "node": {
                                "fields": {
                                    "nodes": [
                                        {
                                            "id": "PVTSSF_status",
                                            "name": "Status",
                                            "options": [
                                                {"id": "opt_backlog", "name": "Backlog"},
                                                {"id": "opt_done", "name": "Done"},
                                            ],
                                        },
                                        {
                                            "id": "PVTSSF_Priority",
                                            "name": "Priority",
                                            "options": [
                                                {"id": "opt_p1", "name": "P1"},
                                                {"id": "opt_p2", "name": "P2"},
                                                {"id": "opt_platform", "name": "Platform"},
                                            ],
                                        },
                                    ]
                                }
                            }
                        }
                    }
                ),
            )

        if "createIssue(" in query:
            num = self.next_issue_number
            self.next_issue_number += 1
            node_id = f"I_{num}"
            self.created_issue_node_ids.append(node_id)
            return (
                200,
                {},
                json.dumps(
                    {
                        "data": {
                            "createIssue": {
                                "issue": {
                                    "id": node_id,
                                    "number": num,
                                    "title": variables["title"],
                                }
                            }
                        }
                    }
                ),
            )

        if "addProjectV2ItemById(" in query:
            item_id = f"PVTI_{self.next_item_id}"
            self.next_item_id += 1
            return (
                200,
                {},
                json.dumps({"data": {"addProjectV2ItemById": {"item": {"id": item_id}}}}),
            )

        if "updateProjectV2ItemFieldValue(" in query:
            return (
                200,
                {},
                json.dumps({"data": {"updateProjectV2ItemFieldValue": {"clientMutationId": None}}}),
            )

        if "updateIssue(" in query:
            self.body_updates.append((variables["issueId"], variables["body"]))
            return (
                200,
                {},
                json.dumps({"data": {"updateIssue": {"issue": {"id": variables["issueId"]}}}}),
            )

        if "addBlockedBy" in query or "blockedByIssues" in query:
            self.add_blocked_by_calls.append(
                (variables.get("issueId", ""), variables.get("blockingIssueId", ""))
            )
            return (200, {}, json.dumps({"data": {"addBlockedBy": {"clientMutationId": None}}}))

        return (500, {}, json.dumps({"errors": [{"message": f"Unrouted query: {query[:80]}"}]}))


def _register_milestones(milestone_count: int) -> None:
    """Register sequential REST milestone responses."""
    url = f"{GHES_URL}/api/v3/repos/example-org/acme/milestones"
    for i in range(1, milestone_count + 1):
        responses.add(
            responses.POST,
            url,
            json={"number": i, "node_id": f"MI_{i}", "title": f"M{i}"},
            status=201,
        )


def _build_orchestrator(
    template: TemplateDefinition,
    instance: InstanceConfig,
    state_path: Path,
) -> tuple[PhaseOrchestrator, StateFile]:
    base = GitHubClient(GHES_URL, "tok", write_delay_ms=0)
    gql = GraphQLClient(base)
    rest = RESTClient(base)
    state = StateFile(target=GHES_URL, org=instance.org)
    state.repo = None  # populated by phase 1
    ep = plan(template, instance)
    return (
        PhaseOrchestrator(
            plan=ep,
            gql=gql,
            rest=rest,
            state=state,
            state_path=state_path,
            logger=logging.getLogger("plynth.test"),
        ),
        state,
    )


@responses.activate
def test_phases_e2e_happy_path(
    minimal_template: TemplateDefinition,
    minimal_instance: InstanceConfig,
    tmp_path: Path,
) -> None:
    dispatcher = _GraphQLDispatcher()
    responses.add_callback(
        responses.POST, GRAPHQL_URL, callback=dispatcher, content_type="application/json"
    )
    _register_milestones(milestone_count=2)

    state_path = tmp_path / "state.yaml"
    orch, state = _build_orchestrator(minimal_template, minimal_instance, state_path)
    orch.execute()

    # Phase 1
    assert state.is_phase_complete(PHASE_1_PROJECT_AND_FIELDS)
    assert state.project is not None
    assert state.project.node_id == "PVT_1"
    assert state.project.number == 7
    assert state.repo is not None
    assert state.repo.node_id == "R_1"
    # Status field captured under the synthetic "_status" key
    assert "_status" in state.fields
    assert state.fields["_status"].options["Backlog"] == "opt_backlog"
    assert "priority" in state.fields

    # Phase 2 — milestones via REST
    assert state.is_phase_complete(PHASE_2_MILESTONES)
    assert set(state.milestones.keys()) == {"M1", "M2"}

    # Phase 3 — issue numbers come from the dispatcher (47, 48, 49)
    assert state.is_phase_complete(PHASE_3_ISSUES)
    assert {iss.number for iss in state.issues.values()} == {47, 48, 49}

    # Phase 4
    assert state.is_phase_complete(PHASE_4_PROJECT_ITEMS)
    for iss in state.issues.values():
        assert iss.item_id.startswith("PVTI_")

    # Phase 5 — body update should have run for the two issues with crossrefs.
    assert state.is_phase_complete(PHASE_5_REFERENCES_AND_DEPS)

    # Map node_id → rewritten body and assert each expected rewrite explicitly.
    # Issues are created in template order: 001=#47, 002=#48, 003=#49.
    body_by_node = dict(dispatcher.body_updates)
    issue_002_node = state.issues["002"].node_id
    issue_003_node = state.issues["003"].node_id
    assert body_by_node[issue_002_node] == "Depends on #47 completing."
    assert body_by_node[issue_003_node] == "Final hardening of Acme. After #48."
    # Issue 001 has no crossref so its body should NOT be updated.
    assert state.issues["001"].node_id not in body_by_node

    # Dependency edges: assert exact (issueId, blockingIssueId) pairs, not just count.
    issue_001_node = state.issues["001"].node_id
    expected_edges = {
        # 002 blocked_by 001
        (issue_002_node, issue_001_node),
        # 003 blocked_by 002
        (issue_003_node, issue_002_node),
    }
    assert set(dispatcher.add_blocked_by_calls) == expected_edges

    # The state's recorded dependency edges use template_ids, not node_ids.
    recorded = {(e.blocked, e.blocker) for e in state.dependencies_created}
    assert recorded == {("002", "001"), ("003", "002")}

    # Phase 7 — final state written.
    assert state.is_phase_complete(PHASE_7_STATE_FILE)
    assert state_path.exists()

    # Reload from disk and verify on-disk serialization. A YAML serialization
    # bug would otherwise pass the in-memory assertions above.
    with open(state_path, encoding="utf-8") as f:
        on_disk = StateFile.model_validate(yaml.safe_load(f))
    assert on_disk.project is not None
    assert on_disk.project.node_id == "PVT_1"
    assert on_disk.project.number == 7
    assert set(on_disk.milestones.keys()) == {"M1", "M2"}
    assert set(on_disk.issues.keys()) == {"001", "002", "003"}
    assert {iss.number for iss in on_disk.issues.values()} == {47, 48, 49}
    assert "_status" in on_disk.fields
    assert on_disk.fields["_status"].options["Backlog"] == "opt_backlog"
    on_disk_edges = {(e.blocked, e.blocker) for e in on_disk.dependencies_created}
    assert on_disk_edges == {("002", "001"), ("003", "002")}
    for phase in (
        PHASE_1_PROJECT_AND_FIELDS,
        PHASE_2_MILESTONES,
        PHASE_3_ISSUES,
        PHASE_4_PROJECT_ITEMS,
        PHASE_5_REFERENCES_AND_DEPS,
        PHASE_7_STATE_FILE,
    ):
        assert on_disk.is_phase_complete(phase)


@responses.activate
def test_phases_e2e_resume_from_disk_is_noop(
    minimal_template: TemplateDefinition,
    minimal_instance: InstanceConfig,
    tmp_path: Path,
) -> None:
    """After a successful run, building a fresh orchestrator from the on-disk
    state file should issue no API calls — exercising the persisted resume path."""
    dispatcher = _GraphQLDispatcher()
    responses.add_callback(
        responses.POST, GRAPHQL_URL, callback=dispatcher, content_type="application/json"
    )
    _register_milestones(milestone_count=2)

    state_path = tmp_path / "state.yaml"
    orch, _ = _build_orchestrator(minimal_template, minimal_instance, state_path)
    orch.execute()

    first_run_call_count = len(responses.calls)
    assert first_run_call_count > 0

    # Build a fresh orchestrator by loading state from disk — simulating a
    # restart. This is what `cli._init_or_load_state` does in production.
    with open(state_path, encoding="utf-8") as f:
        loaded_state = StateFile.model_validate(yaml.safe_load(f))

    base = GitHubClient(GHES_URL, "tok", write_delay_ms=0)
    fresh_orch = PhaseOrchestrator(
        plan=plan(minimal_template, minimal_instance),
        gql=GraphQLClient(base),
        rest=RESTClient(base),
        state=loaded_state,
        state_path=state_path,
        logger=logging.getLogger("plynth.test"),
    )
    fresh_orch.execute()

    # No new API calls should have been issued — every phase already complete.
    assert len(responses.calls) == first_run_call_count


# ── github.com target ─────────────────────────────────────────────

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
GITHUB_MILESTONE_URL = "https://api.github.com/repos/example-org/acme/milestones"


def _build_orchestrator_with_target(
    template: TemplateDefinition,
    instance: InstanceConfig,
    state_path: Path,
    target: str,
) -> tuple[PhaseOrchestrator, StateFile]:
    base = GitHubClient(target, "tok", write_delay_ms=0)
    gql = GraphQLClient(base)
    rest = RESTClient(base)
    state = StateFile(target=target, org=instance.org)
    state.repo = None
    ep = plan(template, instance)
    return (
        PhaseOrchestrator(
            plan=ep,
            gql=gql,
            rest=rest,
            state=state,
            state_path=state_path,
            logger=logging.getLogger("plynth.test"),
        ),
        state,
    )


@responses.activate
def test_phases_e2e_against_github_com(
    minimal_template: TemplateDefinition,
    minimal_instance: InstanceConfig,
    tmp_path: Path,
) -> None:
    """The same happy path against target='github.com' must hit api.github.com
    URLs (no /api/v3 prefix) and succeed."""
    dispatcher = _GraphQLDispatcher()
    responses.add_callback(
        responses.POST,
        GITHUB_GRAPHQL_URL,
        callback=dispatcher,
        content_type="application/json",
    )
    for i in range(1, 3):
        responses.add(
            responses.POST,
            GITHUB_MILESTONE_URL,
            json={"number": i, "node_id": f"MI_{i}", "title": f"M{i}"},
            status=201,
        )

    # Override the target in the loaded instance so the planner emits a
    # github.com plan — fixture is GHES-shaped.
    instance = minimal_instance.model_copy(update={"target": "github.com"})

    orch, state = _build_orchestrator_with_target(
        minimal_template, instance, tmp_path / "state.yaml", "github.com"
    )
    orch.execute()

    # The mocked URLs above are the only ones registered; if the engine had
    # used the GHES-shaped paths, `responses` would have raised
    # ConnectionError. Verify Phase 1+2 finished as a final sanity check.
    assert state.is_phase_complete(PHASE_1_PROJECT_AND_FIELDS)
    assert state.is_phase_complete(PHASE_2_MILESTONES)
    # And confirm at least one call hit each api.github.com endpoint.
    urls_called = [call.request.url for call in responses.calls]
    assert any(url.startswith(GITHUB_GRAPHQL_URL) for url in urls_called)
    assert any(url.startswith(GITHUB_MILESTONE_URL) for url in urls_called)
