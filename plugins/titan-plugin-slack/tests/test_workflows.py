from pathlib import Path

import yaml


def test_summarize_slack_target_workflow_structure() -> None:
    workflow_path = (
        Path(__file__).parent.parent / "titan_plugin_slack" / "workflows" / "summarize-slack-target.yaml"
    )

    with open(workflow_path, encoding="utf-8") as handle:
        workflow = yaml.safe_load(handle)

    assert workflow["name"] == "Summarize Slack Target"
    assert workflow["params"]["slack_history_limit"] == 30
    assert [step["id"] for step in workflow["steps"]] == [
        "validate_connection",
        "select_target",
        "ensure_target_conversation",
        "read_recent_messages",
        "ai_summarize_messages",
    ]
    assert workflow["steps"][1]["step"] == "select_target"
    assert workflow["steps"][3]["params"]["slack_history_limit"] == "${slack_history_limit}"


def test_post_message_workflow_structure() -> None:
    workflow_path = (
        Path(__file__).parent.parent / "titan_plugin_slack" / "workflows" / "post-message.yaml"
    )

    with open(workflow_path, encoding="utf-8") as handle:
        workflow = yaml.safe_load(handle)

    assert workflow["name"] == "Post Slack Message"
    assert [step["id"] for step in workflow["steps"]] == [
        "validate_connection",
        "select_target",
        "prepare_destination",
        "compose_message",
        "format_message",
        "post_message",
    ]
    assert workflow["steps"][1]["step"] == "select_default_or_search_channel_target"
    assert workflow["steps"][3]["step"] == "prompt_message_body"
    assert workflow["steps"][4]["step"] == "format_markdown_message"
    assert all("on_error" not in step for step in workflow["steps"])
