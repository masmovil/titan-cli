"""Contract tests for the plan-jira-issue workflow."""

from pathlib import Path

import yaml


WORKFLOW_PATH = (
    Path(__file__).parent.parent.parent
    / "titan_plugin_jira"
    / "workflows"
    / "plan-jira-issue.yaml"
)


def _load_workflow() -> dict:
    with WORKFLOW_PATH.open(encoding="utf-8") as workflow_file:
        return yaml.safe_load(workflow_file)


def test_plan_workflow_executes_issue_before_creating_pull_request():
    workflow = _load_workflow()

    step_ids = [step["id"] for step in workflow["steps"]]

    assert step_ids == [
        "select_issue",
        "get_issue",
        "get_comments",
        "build_task_context",
        "plan_with_cli",
        "confirm_and_assign_issue",
        "create_issue_worktree",
        "activate_issue_worktree",
        "implement_with_cli",
        "create_pull_request",
        "cleanup_issue_worktree",
    ]


def test_branch_worktree_is_created_from_develop_using_the_issue_key():
    workflow = _load_workflow()
    steps_by_id = {step["id"]: step for step in workflow["steps"]}

    assert workflow["params"] == {
        "base_branch": "develop",
        "branch_prefix": "feature",
        "remote": "origin",
        "pr_base_branch": "develop",
    }
    assert steps_by_id["create_issue_worktree"]["params"] == {
        "base_branch": "${base_branch}",
        "new_branch": "${branch_prefix}/${jira_issue_key}",
    }
    assert steps_by_id["activate_issue_worktree"]["step"] == (
        "activate_worktree_context"
    )
    assert steps_by_id["cleanup_issue_worktree"]["step"] == ("cleanup_worktree_context")


def test_implementation_step_requires_unit_test_context_and_stops_on_decline():
    workflow = _load_workflow()
    implementation_step = next(
        step for step in workflow["steps"] if step["id"] == "implement_with_cli"
    )

    assert implementation_step["plugin"] == "core"
    assert implementation_step["step"] == "ai_code_assistant"
    assert implementation_step["params"] == {
        "context_key": "jira_implementation_context",
        "cli_preference": "auto",
        "ask_confirmation": True,
        "fail_on_decline": True,
    }
    assert implementation_step["on_error"] == "fail"


def test_pull_request_step_reuses_existing_workflow():
    workflow = _load_workflow()
    pull_request_step = next(
        step for step in workflow["steps"] if step["id"] == "create_pull_request"
    )

    assert pull_request_step == {
        "id": "create_pull_request",
        "name": "Create Pull Request",
        "workflow": "create-pr-ai",
    }
