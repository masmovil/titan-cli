from unittest.mock import MagicMock, patch

from titan_cli.ai.router import AIExecutionError, AIExecutionSuccess, AIProviderType, AIRouteDecision
from titan_cli.core.result import ClientSuccess
from titan_cli.engine import Error, Skip
from titan_plugin_git.steps.ai_commit_message_step import ai_generate_commit_message
from titan_plugin_git.models import GitStatus


def _build_context(selected_files=None, ai_result=None):
    ctx = MagicMock()
    ctx.textual = MagicMock()
    ctx.git = MagicMock()

    git_status = GitStatus(
        branch="feature/test",
        is_clean=False,
        modified_files=["src/main.py"],
        untracked_files=["README.md"],
        staged_files=["staged.py"],
        ahead=0,
        behind=0,
    )

    values = {
        "git_status": git_status,
        "selected_files": selected_files,
    }
    ctx.get.side_effect = lambda key, default=None: values.get(key, default)

    ctx.ai_router = MagicMock()
    ctx.ai_router.generate_text.return_value = ai_result or AIExecutionSuccess(
        decision=AIRouteDecision(provider=AIProviderType.REMOTE),
        data="feat: Add selected change",
    )
    ctx.textual.ask_confirm.return_value = True
    return ctx


def test_ai_commit_message_uses_selected_files_for_diff_and_prompt():
    ctx = _build_context(selected_files=["src/main.py"])
    ctx.git.get_uncommitted_diff_for_files.return_value = ClientSuccess(
        data="diff --git a/src/main.py b/src/main.py",
        message="ok",
    )

    with patch("titan_plugin_git.steps.ai_commit_message_step.build_ai_commit_prompt") as build_prompt:
        build_prompt.return_value = "prompt"

        result = ai_generate_commit_message(ctx)

    assert result.metadata["commit_message"] == "feat: Add selected change"
    ctx.git.get_uncommitted_diff_for_files.assert_called_once_with(["src/main.py"])
    ctx.git.get_uncommitted_diff.assert_not_called()
    build_prompt.assert_called_once_with(
        "diff --git a/src/main.py b/src/main.py",
        ["src/main.py"],
        max_diff_chars=8000,
    )


def test_ai_commit_message_uses_full_file_list_when_no_selection_exists():
    ctx = _build_context(selected_files=None)
    ctx.git.get_uncommitted_diff_for_files.return_value = ClientSuccess(
        data="diff --git a/src/main.py b/src/main.py",
        message="ok",
    )

    with patch("titan_plugin_git.steps.ai_commit_message_step.build_ai_commit_prompt") as build_prompt:
        build_prompt.return_value = "prompt"

        result = ai_generate_commit_message(ctx)

    assert result.metadata["commit_message"] == "feat: Add selected change"
    ctx.git.get_uncommitted_diff_for_files.assert_called_once_with(
        ["src/main.py", "README.md", "staged.py"]
    )
    ctx.git.get_uncommitted_diff.assert_not_called()
    build_prompt.assert_called_once_with(
        "diff --git a/src/main.py b/src/main.py",
        ["src/main.py", "README.md", "staged.py"],
        max_diff_chars=8000,
    )


def test_ai_commit_message_routes_through_the_ai_facade():
    """The step must not pick a provider itself - it hands its own policy to the façade."""
    ctx = _build_context(selected_files=["src/main.py"])
    ctx.git.get_uncommitted_diff_for_files.return_value = ClientSuccess(data="diff", message="ok")

    with patch("titan_plugin_git.steps.ai_commit_message_step.build_ai_commit_prompt") as build_prompt:
        build_prompt.return_value = "the prompt"
        ai_generate_commit_message(ctx)

    args, kwargs = ctx.ai_router.generate_text.call_args
    assert args[0] == "the prompt"
    assert kwargs["policy"] is ai_generate_commit_message


def test_ai_commit_message_skips_when_ai_is_turned_off():
    ctx = _build_context(
        selected_files=["src/main.py"],
        ai_result=AIExecutionError(
            error_message="AI is turned off for this task.",
            error_code="AI_DISABLED",
            log_level="info",
        ),
    )
    ctx.git.get_uncommitted_diff_for_files.return_value = ClientSuccess(data="diff", message="ok")

    with patch("titan_plugin_git.steps.ai_commit_message_step.build_ai_commit_prompt") as build_prompt:
        build_prompt.return_value = "prompt"
        result = ai_generate_commit_message(ctx)

    assert isinstance(result, Skip)
    assert "turned off" in result.message


def test_ai_commit_message_errors_when_configured_provider_is_unavailable():
    ctx = _build_context(
        selected_files=["src/main.py"],
        ai_result=AIExecutionError(
            error_message="task preference for 'commit_message' is no longer available",
            error_code="PROVIDER_UNAVAILABLE",
        ),
    )
    ctx.git.get_uncommitted_diff_for_files.return_value = ClientSuccess(data="diff", message="ok")

    with patch("titan_plugin_git.steps.ai_commit_message_step.build_ai_commit_prompt") as build_prompt:
        build_prompt.return_value = "prompt"
        result = ai_generate_commit_message(ctx)

    assert isinstance(result, Error)
    assert "no longer available" in result.message


def test_ai_commit_message_errors_without_the_ai_facade():
    ctx = _build_context(selected_files=["src/main.py"])
    ctx.ai_router = None

    result = ai_generate_commit_message(ctx)

    assert isinstance(result, Error)
    ctx.git.get_uncommitted_diff_for_files.assert_not_called()
