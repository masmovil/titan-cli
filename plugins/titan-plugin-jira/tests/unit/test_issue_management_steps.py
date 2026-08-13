from unittest.mock import Mock

from titan_cli.core.result import ClientError, ClientSuccess
from titan_cli.engine import Error, Success, WorkflowContext
from titan_plugin_jira.models import UIJiraTransition, UIJiraVersion
from titan_plugin_jira.steps.issue_management_steps import (
    assign_fix_version_step,
    create_version_step,
    ensure_version_exists_step,
    get_transitions_step,
    transition_issue_step,
    verify_issue_has_fix_version_step,
    verify_issue_state_step,
)


class MockTextual:
    def __init__(self):
        self.begin_step = Mock()
        self.end_step = Mock()
        self.error_text = Mock()
        self.success_text = Mock()

    def loading(self, _message):
        class Loader:
            def __enter__(self):
                return None

            def __exit__(self, exc_type, exc, tb):
                return False

        return Loader()


def make_context(mock_jira=None, **data):
    ctx = WorkflowContext(textual=MockTextual(), jira=mock_jira)
    ctx.data.update(data)
    return ctx


def test_get_transitions_step_success():
    jira = Mock()
    transitions = [UIJiraTransition(id="1", name="Move to QA", to_status="QA", to_status_icon="🟢")]
    jira.get_transitions.return_value = ClientSuccess(data=transitions, message="ok")
    ctx = make_context(jira, jira_issue_key="TEST-1")

    result = get_transitions_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {"jira_transitions": transitions}


def test_transition_issue_step_success():
    jira = Mock()
    jira.transition_issue.return_value = ClientSuccess(data=None, message="ok")
    ctx = make_context(jira, jira_issue_key="TEST-1", target_status="QA")

    result = transition_issue_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {"transition_target_status": "QA"}


def test_transition_issue_step_passes_fields_and_update():
    jira = Mock()
    jira.transition_issue.return_value = ClientSuccess(data=None, message="ok")
    fields = {"customfield_11281": {"id": "19077"}}
    update = {"labels": [{"add": "qa"}]}
    ctx = make_context(
        jira,
        jira_issue_key="TEST-1",
        target_status="QA",
        transition_comment="Completed",
        fields=fields,
        update=update,
    )

    result = transition_issue_step(ctx)

    assert isinstance(result, Success)
    jira.transition_issue.assert_called_once_with(
        "TEST-1",
        "QA",
        comment="Completed",
        fields=fields,
        update=update,
    )


def test_verify_issue_state_step_mismatch_returns_error(sample_ui_issue):
    jira = Mock()
    jira.get_issue.return_value = ClientSuccess(data=sample_ui_issue, message="ok")
    ctx = make_context(jira, jira_issue_key="TEST-123", expected_status="Done")

    result = verify_issue_state_step(ctx)

    assert isinstance(result, Error)
    assert "expected 'Done'" in result.message


def test_create_version_step_success():
    jira = Mock()
    version = UIJiraVersion(id="10", name="1.0.0", description="", released=False, release_date="Not set")
    jira.create_version.return_value = ClientSuccess(data=version, message="ok")
    ctx = make_context(jira, project_key="TEST", version_name="1.0.0")

    result = create_version_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {"version": version, "version_id": "10", "version_name": "1.0.0"}


def test_ensure_version_exists_step_success():
    jira = Mock()
    version = UIJiraVersion(id="10", name="1.0.0", description="", released=False, release_date="Not set")
    jira.ensure_version_exists.return_value = ClientSuccess(data=version, message="ok")
    ctx = make_context(jira, project_key="TEST", version_name="1.0.0")

    result = ensure_version_exists_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {"version": version, "version_id": "10", "version_name": "1.0.0"}


def test_assign_fix_version_step_success():
    jira = Mock()
    jira.assign_fix_version.return_value = ClientSuccess(data=None, message="ok")
    ctx = make_context(jira, jira_issue_key="TEST-1", version_name="1.0.0", project_key="TEST")

    result = assign_fix_version_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {"assigned_fix_version": "1.0.0"}


def test_verify_issue_has_fix_version_step_success(sample_ui_issue):
    jira = Mock()
    sample_ui_issue.fix_versions = ["1.0.0"]
    jira.get_issue.return_value = ClientSuccess(data=sample_ui_issue, message="ok")
    ctx = make_context(jira, jira_issue_key="TEST-123", version_name="1.0.0")

    result = verify_issue_has_fix_version_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata == {"verified_jira_issue": sample_ui_issue}


def test_verify_issue_has_fix_version_step_missing_version_returns_error(sample_ui_issue):
    jira = Mock()
    jira.get_issue.return_value = ClientSuccess(data=sample_ui_issue, message="ok")
    ctx = make_context(jira, jira_issue_key="TEST-123", version_name="2.0.0")

    result = verify_issue_has_fix_version_step(ctx)

    assert isinstance(result, Error)


def test_get_transitions_step_client_error():
    jira = Mock()
    jira.get_transitions.return_value = ClientError(error_message="boom")
    ctx = make_context(jira, jira_issue_key="TEST-1")

    result = get_transitions_step(ctx)

    assert isinstance(result, Error)
