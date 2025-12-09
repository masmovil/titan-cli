"""
Tests for AI Agent Analysis Steps
"""

import pytest
from unittest.mock import Mock, MagicMock
from titan_cli.engine import WorkflowContext, Success, Error, Skip
from titan_cli.agents.steps import (
    ai_analyze_changes_step,
    ai_suggest_commit_message_step,
)


class TestAIAnalyzeChangesStep:
    """Tests for ai_analyze_changes_step."""

    def test_skip_when_no_ai_configured(self):
        """Should skip if AI is not configured."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = None

        result = ai_analyze_changes_step(ctx)

        assert isinstance(result, Skip)
        assert "AI not configured" in result.message

    def test_skip_when_no_git_data(self):
        """Should skip if no git data in context."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()
        ctx.data = {}

        result = ai_analyze_changes_step(ctx)

        assert isinstance(result, Skip)
        assert "No git data" in result.message

    def test_skip_when_working_directory_clean(self):
        """Should skip if working directory is clean."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        # Mock git status (clean)
        git_status = Mock()
        git_status.is_clean = True
        ctx.data = {"git_status": git_status}

        result = ai_analyze_changes_step(ctx)

        assert isinstance(result, Skip)
        assert "clean" in result.message.lower()

    def test_success_with_git_status(self):
        """Should analyze successfully with git status."""
        ctx = WorkflowContext(secrets=Mock())

        # Mock AI
        mock_ai = Mock()
        mock_ai.generate = Mock(return_value="Analysis: Code looks good!")
        ctx.ai = mock_ai

        # Mock git status (dirty)
        git_status = Mock()
        git_status.is_clean = False
        git_status.branch = "main"
        git_status.modified_files = ["file1.py", "file2.py"]
        git_status.untracked_files = []
        ctx.data = {"git_status": git_status}

        result = ai_analyze_changes_step(ctx)

        assert isinstance(result, Success)
        assert "ai_analysis" in result.metadata
        assert result.metadata["ai_analysis"] == "Analysis: Code looks good!"
        mock_ai.generate.assert_called_once()

    def test_error_on_ai_failure(self):
        """Should return Error if AI generation fails."""
        ctx = WorkflowContext(secrets=Mock())

        # Mock AI that raises exception
        mock_ai = Mock()
        mock_ai.generate = Mock(side_effect=Exception("AI service unavailable"))
        ctx.ai = mock_ai

        # Mock git status
        git_status = Mock()
        git_status.is_clean = False
        git_status.branch = "main"
        git_status.modified_files = ["file.py"]
        git_status.untracked_files = []
        ctx.data = {"git_status": git_status}

        result = ai_analyze_changes_step(ctx)

        assert isinstance(result, Error)
        assert "AI service unavailable" in result.message


class TestAISuggestCommitMessageStep:
    """Tests for ai_suggest_commit_message_step."""

    def test_skip_when_no_ai(self):
        """Should skip if AI not configured."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = None

        result = ai_suggest_commit_message_step(ctx)

        assert isinstance(result, Skip)
        assert "AI not configured" in result.message

    def test_skip_when_clean(self):
        """Should skip if working directory is clean."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        git_status = Mock()
        git_status.is_clean = True
        ctx.data = {"git_status": git_status}

        result = ai_suggest_commit_message_step(ctx)

        assert isinstance(result, Skip)

    def test_generates_commit_message(self):
        """Should generate conventional commit message."""
        ctx = WorkflowContext(secrets=Mock())

        # Mock AI
        mock_ai = Mock()
        mock_ai.generate = Mock(return_value="feat(api): add user authentication")
        ctx.ai = mock_ai

        # Mock git status
        git_status = Mock()
        git_status.is_clean = False
        git_status.modified_files = ["api/auth.py"]
        git_status.branch = "feature/auth"
        ctx.data = {"git_status": git_status}

        result = ai_suggest_commit_message_step(ctx)

        assert isinstance(result, Success)
        assert "suggested_commit_message" in result.metadata
        assert "commit_message" in result.metadata  # Auto-populated
        assert result.metadata["commit_message"] == "feat(api): add user authentication"

    def test_cleans_up_message(self):
        """Should clean up AI-generated message (remove markdown, etc)."""
        ctx = WorkflowContext(secrets=Mock())

        # Mock AI that returns message with markdown
        mock_ai = Mock()
        mock_ai.generate = Mock(return_value="```\nfeat: add feature\n```")
        ctx.ai = mock_ai

        git_status = Mock()
        git_status.is_clean = False
        git_status.modified_files = ["file.py"]
        ctx.data = {"git_status": git_status}

        result = ai_suggest_commit_message_step(ctx)

        assert isinstance(result, Success)
        # Should have removed backticks
        assert "`" not in result.metadata["commit_message"]
        assert result.metadata["commit_message"] == "feat: add feature"

    def test_uses_commit_type_hint(self):
        """Should pass commit type hint to AI."""
        ctx = WorkflowContext(secrets=Mock())

        mock_ai = Mock()
        mock_ai.generate = Mock(return_value="fix: resolve bug")
        ctx.ai = mock_ai

        git_status = Mock()
        git_status.is_clean = False
        git_status.modified_files = ["bug_fix.py"]
        ctx.data = {
            "git_status": git_status,
            "commit_type_hint": "fix"
        }

        result = ai_suggest_commit_message_step(ctx)

        assert isinstance(result, Success)
        # Verify prompt included the hint
        call_args = mock_ai.generate.call_args
        assert "fix" in call_args.kwargs["prompt"].lower()

    def test_error_on_ai_failure(self):
        """Should return Error if AI fails."""
        ctx = WorkflowContext(secrets=Mock())

        mock_ai = Mock()
        mock_ai.generate = Mock(side_effect=Exception("Network error"))
        ctx.ai = mock_ai

        git_status = Mock()
        git_status.is_clean = False
        git_status.modified_files = ["file.py"]
        ctx.data = {"git_status": git_status}

        result = ai_suggest_commit_message_step(ctx)

        assert isinstance(result, Error)
        assert "Network error" in result.message
