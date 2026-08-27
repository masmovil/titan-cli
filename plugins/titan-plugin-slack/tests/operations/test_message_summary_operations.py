from titan_plugin_slack.models import UISlackMessage
from titan_plugin_slack.operations.message_summary_operations import (
    build_summary_prompt,
    format_messages_as_transcript,
    truncate_transcript_for_summary,
)


def test_format_messages_as_transcript_includes_target_and_messages() -> None:
    messages = [
        UISlackMessage(ts="1718013600.000001", text="Hello", user="U123"),
        UISlackMessage(ts="1718013660.000002", text="World", user="U456"),
    ]

    transcript = format_messages_as_transcript(messages, target_name="general")

    assert "Target: general" in transcript
    assert "U123: Hello" in transcript
    assert "U456: World" in transcript


def test_truncate_transcript_for_summary_marks_truncation() -> None:
    transcript = "a" * 100

    truncated = truncate_transcript_for_summary(transcript, max_chars=40)

    assert truncated.endswith("[Transcript truncated]")
    assert len(truncated) <= 40


def test_build_summary_prompt_mentions_target() -> None:
    prompt = build_summary_prompt("general", "message transcript")

    assert "general" in prompt
    assert "message transcript" in prompt
