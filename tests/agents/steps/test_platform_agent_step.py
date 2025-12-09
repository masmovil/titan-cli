"""
Tests for Platform Agent Workflow Steps
"""

import pytest
from unittest.mock import Mock, patch
from titan_cli.engine import WorkflowContext, Success, Error, Skip
from titan_cli.agents.steps.platform_agent_step import (
    platform_agent_analysis_step,
    platform_agent_suggest_commit_step,
)


class TestPlatformAgentAnalysisStep:
    """Tests for platform_agent_analysis_step."""

    def test_skip_when_no_ai(self):
        """Should skip if AI not configured."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = None

        result = platform_agent_analysis_step(ctx)

        assert isinstance(result, Skip)
        assert "AI not configured" in result.message

    @patch('titan_cli.agents.steps.platform_agent_step.PlatformAgent')
    def test_loads_agent_from_config(self, mock_agent_class):
        """Should load PlatformAgent from TOML config."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        # Mock agent that skips (no data)
        mock_agent = Mock()
        mock_agent.run = Mock(return_value=Skip("No data"))
        mock_agent_class.from_toml = Mock(return_value=mock_agent)

        platform_agent_analysis_step(ctx, agent_config="custom.toml")

        # Verify agent was loaded with custom config
        mock_agent_class.from_toml.assert_called_once_with("custom.toml")
        mock_agent.run.assert_called_once()

    @patch('titan_cli.agents.steps.platform_agent_step.PlatformAgent')
    def test_runs_agent_in_analysis_mode(self, mock_agent_class):
        """Should run agent in analysis mode."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        mock_agent = Mock()
        mock_agent.run = Mock(return_value=Success("Analysis done"))
        mock_agent_class.from_toml = Mock(return_value=mock_agent)

        platform_agent_analysis_step(ctx)

        # Verify mode="analysis" was passed
        call_args = mock_agent.run.call_args
        assert call_args.kwargs["mode"] == "analysis"

    @patch('titan_cli.agents.steps.platform_agent_step.PlatformAgent')
    def test_passes_custom_task(self, mock_agent_class):
        """Should pass custom task to agent."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        mock_agent = Mock()
        mock_agent.run = Mock(return_value=Success("Done"))
        mock_agent_class.from_toml = Mock(return_value=mock_agent)

        platform_agent_analysis_step(
            ctx,
            task="Custom analysis task"
        )

        # Verify custom task was passed
        call_args = mock_agent.run.call_args
        assert "Custom analysis task" in call_args.kwargs["user_context"]

    @patch('titan_cli.agents.steps.platform_agent_step.PlatformAgent')
    def test_adds_standard_metadata_key(self, mock_agent_class):
        """Should add agent_analysis key to metadata."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        mock_agent = Mock()
        mock_agent.run = Mock(return_value=Success(
            "Analysis result",
            metadata={"mode": "analysis"}
        ))
        mock_agent_class.from_toml = Mock(return_value=mock_agent)

        result = platform_agent_analysis_step(ctx)

        assert isinstance(result, Success)
        assert "agent_analysis" in result.metadata
        assert result.metadata["agent_analysis"] == "Analysis result"

    @patch('titan_cli.agents.steps.platform_agent_step.PlatformAgent')
    def test_returns_error_on_agent_failure(self, mock_agent_class):
        """Should return Error if agent fails."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        mock_agent_class.from_toml = Mock(
            side_effect=Exception("Config error")
        )

        result = platform_agent_analysis_step(ctx)

        assert isinstance(result, Error)
        assert "Config error" in result.message


class TestPlatformAgentSuggestCommitStep:
    """Tests for platform_agent_suggest_commit_step."""

    def test_skip_when_no_ai(self):
        """Should skip if AI not configured."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = None

        result = platform_agent_suggest_commit_step(ctx)

        assert isinstance(result, Skip)
        assert "AI not configured" in result.message

    def test_skip_when_clean(self):
        """Should skip if working directory is clean."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        git_status = Mock()
        git_status.is_clean = True
        ctx.data = {"git_status": git_status}

        result = platform_agent_suggest_commit_step(ctx)

        assert isinstance(result, Skip)
        assert "clean" in result.message.lower()

    @patch('titan_cli.agents.steps.platform_agent_step.PlatformAgent')
    def test_generates_commit_message(self, mock_agent_class):
        """Should generate commit message using PlatformAgent."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        git_status = Mock()
        git_status.is_clean = False
        git_status.modified_files = ["file.py"]
        ctx.data = {"git_status": git_status}

        # Mock agent returns commit message
        mock_agent = Mock()
        mock_agent.run = Mock(return_value=Success(
            "feat(api): add user authentication"
        ))
        mock_agent_class.from_toml = Mock(return_value=mock_agent)

        result = platform_agent_suggest_commit_step(ctx)

        assert isinstance(result, Success)
        assert "suggested_commit_message" in result.metadata
        assert "commit_message" in result.metadata
        assert "feat(api)" in result.metadata["commit_message"]

    @patch('titan_cli.agents.steps.platform_agent_step.PlatformAgent')
    def test_cleans_up_message(self, mock_agent_class):
        """Should clean up AI response (remove markdown, etc)."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        git_status = Mock()
        git_status.is_clean = False
        git_status.modified_files = ["file.py"]
        ctx.data = {"git_status": git_status}

        # Mock agent returns message with markdown
        mock_agent = Mock()
        mock_agent.run = Mock(return_value=Success(
            "```\nfeat: add feature\n```"
        ))
        mock_agent_class.from_toml = Mock(return_value=mock_agent)

        result = platform_agent_suggest_commit_step(ctx)

        assert isinstance(result, Success)
        # Should have removed backticks
        assert "`" not in result.metadata["commit_message"]
        assert result.metadata["commit_message"] == "feat: add feature"

    @patch('titan_cli.agents.steps.platform_agent_step.PlatformAgent')
    def test_removes_commit_prefix(self, mock_agent_class):
        """Should remove 'commit:' prefix if AI added it."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        git_status = Mock()
        git_status.is_clean = False
        git_status.modified_files = ["file.py"]
        ctx.data = {"git_status": git_status}

        mock_agent = Mock()
        mock_agent.run = Mock(return_value=Success(
            "commit: fix: resolve bug"
        ))
        mock_agent_class.from_toml = Mock(return_value=mock_agent)

        result = platform_agent_suggest_commit_step(ctx)

        assert isinstance(result, Success)
        assert result.metadata["commit_message"] == "fix: resolve bug"

    @patch('titan_cli.agents.steps.platform_agent_step.PlatformAgent')
    def test_takes_first_line_if_multiline(self, mock_agent_class):
        """Should take only first line if AI returns multiline."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        git_status = Mock()
        git_status.is_clean = False
        git_status.modified_files = ["file.py"]
        ctx.data = {"git_status": git_status}

        mock_agent = Mock()
        mock_agent.run = Mock(return_value=Success(
            "feat: add feature\n\nDetailed explanation here"
        ))
        mock_agent_class.from_toml = Mock(return_value=mock_agent)

        result = platform_agent_suggest_commit_step(ctx)

        assert isinstance(result, Success)
        assert result.metadata["commit_message"] == "feat: add feature"
        assert "\n" not in result.metadata["commit_message"]

    @patch('titan_cli.agents.steps.platform_agent_step.PlatformAgent')
    def test_error_on_agent_failure(self, mock_agent_class):
        """Should return Error if agent fails."""
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        git_status = Mock()
        git_status.is_clean = False
        git_status.modified_files = ["file.py"]
        ctx.data = {"git_status": git_status}

        mock_agent_class.from_toml = Mock(
            side_effect=Exception("Agent error")
        )

        result = platform_agent_suggest_commit_step(ctx)

        assert isinstance(result, Error)
        assert "Agent error" in result.message
