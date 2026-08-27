from unittest.mock import MagicMock

from titan_cli.ai.router import (
    AIExecutionError,
    AIExecutionSuccess,
    AIProviderType,
    AIRouteDecision,
)
from titan_cli.core.result import ClientSuccess
from titan_cli.engine import Error, Skip, Success
from titan_cli.engine.context import WorkflowContext
from titan_plugin_slack.models import UISlackConversation, UISlackMessage, UISlackTarget
from titan_plugin_slack.steps.summary_steps import (
    ai_summarize_messages_step,
    ensure_target_conversation_step,
    read_recent_messages_step,
    select_target_step,
)


def _build_context() -> WorkflowContext:
    ctx = WorkflowContext()
    ctx.textual = MagicMock()

    loading_mock = MagicMock()
    loading_mock.__enter__ = MagicMock(return_value=loading_mock)
    loading_mock.__exit__ = MagicMock(return_value=None)
    ctx.textual.loading = MagicMock(return_value=loading_mock)
    return ctx


def _ai_router(result) -> MagicMock:
    """A façade stub whose generate_text returns the given execution result."""
    router = MagicMock()
    router.generate_text.return_value = result
    return router


def _generated(text: str) -> AIExecutionSuccess:
    return AIExecutionSuccess(
        decision=AIRouteDecision(provider=AIProviderType.REMOTE), data=text
    )


def test_select_target_returns_error_for_short_query() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.textual.ask_text.return_value = "g"

    result = select_target_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "Enter at least 2 characters to search Slack targets."


def test_select_target_returns_selected_target_metadata() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.textual.ask_text.return_value = "gabriel"
    user_target = UISlackTarget(
        target_type="user",
        target_id="U123",
        target_name="Gabriel Garcia Lopez",
    )
    ctx.slack.search_users.return_value = ClientSuccess(
            data=[MagicMock(id="U123", name="gabriel", real_name="Gabriel Garcia Lopez")]
        )
    ctx.slack.search_channels.return_value = ClientSuccess(data=[])
    ctx.textual.ask_option.return_value = user_target

    result = select_target_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["slack_target"] == user_target
    assert result.metadata["slack_target_type"] == "user"


def test_ensure_target_conversation_uses_channel_target_directly() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.data["slack_target"] = UISlackTarget(
        target_type="channel",
        target_id="C123",
        target_name="general",
    )

    result = ensure_target_conversation_step(ctx)

    assert isinstance(result, Success)
    conversation = result.metadata["slack_conversation"]
    assert isinstance(conversation, UISlackConversation)
    assert conversation.id == "C123"


def test_read_recent_messages_returns_messages() -> None:
    ctx = _build_context()
    ctx.slack = MagicMock()
    ctx.data["slack_conversation_id"] = "C123"
    ctx.slack.read_conversation.return_value = ClientSuccess(
        data=([
            UISlackMessage(ts="1", text="Hello", user="U123"),
        ], None, False)
    )

    result = read_recent_messages_step(ctx)

    assert isinstance(result, Success)
    assert len(result.metadata["slack_messages"]) == 1
    ctx.slack.read_conversation.assert_called_once_with("C123", limit=30)


def test_ai_summarize_messages_skips_without_ai() -> None:
    ctx = _build_context()
    ctx.data["slack_messages"] = [UISlackMessage(ts="1", text="Hello", user="U123")]

    result = ai_summarize_messages_step(ctx)

    assert isinstance(result, Skip)


def test_ai_summarize_messages_skips_when_ai_is_turned_off() -> None:
    ctx = _build_context()
    ctx.ai_router = _ai_router(
        AIExecutionError(
            error_message="AI is turned off for this task.",
            error_code="AI_DISABLED",
            log_level="info",
        )
    )
    ctx.data["slack_messages"] = [UISlackMessage(ts="1", text="Hello", user="U123")]

    result = ai_summarize_messages_step(ctx)

    assert isinstance(result, Skip)
    assert "turned off" in result.message


def test_ai_summarize_messages_routes_through_the_ai_facade() -> None:
    ctx = _build_context()
    ctx.ai_router = _ai_router(_generated("Summary text"))
    ctx.data["slack_messages"] = [UISlackMessage(ts="1", text="Hello", user="U123")]

    ai_summarize_messages_step(ctx)

    assert ctx.ai_router.generate_text.call_args.kwargs["policy"] is ai_summarize_messages_step


def test_ai_summarize_messages_returns_summary() -> None:
    ctx = _build_context()
    ctx.ai_router = _ai_router(_generated("Summary text"))
    ctx.data["slack_messages"] = [UISlackMessage(ts="1", text="Hello", user="U123")]
    ctx.data["slack_target_name"] = "general"

    result = ai_summarize_messages_step(ctx)

    assert isinstance(result, Success)
    assert result.metadata["slack_summary"] == "Summary text"


def test_ai_summarize_messages_returns_error_for_empty_summary() -> None:
    ctx = _build_context()
    ctx.ai_router = _ai_router(_generated("   "))
    ctx.data["slack_messages"] = [UISlackMessage(ts="1", text="Hello", user="U123")]

    result = ai_summarize_messages_step(ctx)

    assert isinstance(result, Error)
    assert result.message == "AI returned an empty Slack summary."


def test_ai_summarize_messages_returns_visual_error_for_rate_limit() -> None:
    ctx = _build_context()
    ctx.ai_router = _ai_router(
        AIExecutionError(
            error_message="Rate limit exceeded: 429 RESOURCE_EXHAUSTED",
            error_code="EXECUTION_FAILED",
        )
    )
    ctx.data["slack_messages"] = [UISlackMessage(ts="1", text="Hello", user="U123")]

    result = ai_summarize_messages_step(ctx)

    assert isinstance(result, Error)
    assert result.message == (
        "AI summary is temporarily rate limited by the configured AI provider. "
        "Please wait and try again."
    )
    ctx.textual.error_text.assert_called_once_with(result.message)
    ctx.textual.end_step.assert_called_with("error")
