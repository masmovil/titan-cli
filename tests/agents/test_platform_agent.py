"""
Tests for PlatformAgent
"""

import pytest
from unittest.mock import Mock, MagicMock
from pathlib import Path
from titan_cli.engine import WorkflowContext, Success, Error, Skip
from titan_cli.agents.platform_agent import PlatformAgent


def create_mock_git_status(is_clean=False, branch="main", modified=None, untracked=None):
    """Helper to create a properly mocked git status."""
    mock = Mock()
    mock.is_clean = is_clean
    mock.branch = branch
    mock.modified_files = modified or []
    mock.untracked_files = untracked or []
    return mock


class TestPlatformAgentLoading:
    """Tests for loading PlatformAgent from TOML."""

    def test_from_toml_loads_successfully(self, tmp_path):
        """Should load agent from valid TOML file."""
        # Create temp TOML config
        config_file = tmp_path / "test_agent.toml"
        config_file.write_text("""
[agent]
name = "test_agent"
description = "Test agent"

[prompts]
system = "You are a test assistant"
""")

        agent = PlatformAgent.from_toml(config_file)

        assert agent.name == "test_agent"
        assert agent.description == "Test agent"
        assert agent.config is not None

    def test_from_toml_raises_on_missing_file(self):
        """Should raise FileNotFoundError for missing config."""
        with pytest.raises(FileNotFoundError):
            PlatformAgent.from_toml("nonexistent.toml")


class TestPlatformAgentAnalysisMode:
    """Tests for PlatformAgent in analysis mode."""

    def test_skips_when_no_ai(self, tmp_path):
        """Should skip if AI not configured."""
        config_file = tmp_path / "agent.toml"
        config_file.write_text("""
[agent]
name = "test"
description = "Test"

[prompts]
system = "Test"
""")

        agent = PlatformAgent.from_toml(config_file)
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = None  # No AI

        result = agent.run(ctx, mode="analysis")

        assert isinstance(result, Skip)
        assert "AI not configured" in result.message

    def test_skips_when_no_data(self, tmp_path):
        """Should skip if no data in context."""
        config_file = tmp_path / "agent.toml"
        config_file.write_text("""
[agent]
name = "test"
description = "Test"

[prompts]
system = "Test"
""")

        agent = PlatformAgent.from_toml(config_file)
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()
        ctx.data = {}  # No data

        result = agent.run(ctx, mode="analysis")

        assert isinstance(result, Skip)
        assert "No data" in result.message

    def test_analyzes_git_status_successfully(self, tmp_path):
        """Should analyze git status data successfully."""
        config_file = tmp_path / "agent.toml"
        config_file.write_text("""
[agent]
name = "test"
description = "Test"

[prompts]
analysis_system = "Analyze this data"
""")

        agent = PlatformAgent.from_toml(config_file)
        ctx = WorkflowContext(secrets=Mock())

        # Mock AI
        mock_ai = Mock()
        mock_ai.generate = Mock(return_value="Analysis complete: looks good!")
        ctx.ai = mock_ai

        # Mock git status
        git_status = Mock()
        git_status.is_clean = False
        git_status.branch = "main"
        git_status.modified_files = ["file1.py", "file2.py"]
        git_status.untracked_files = []
        ctx.data = {"git_status": git_status}

        result = agent.run(ctx, mode="analysis")

        assert isinstance(result, Success)
        assert "Analysis complete" in result.message
        assert result.metadata["mode"] == "analysis"
        assert "git_status" in result.metadata["data_keys"]
        mock_ai.generate.assert_called_once()

    def test_uses_custom_user_context(self, tmp_path):
        """Should incorporate user context in prompt."""
        config_file = tmp_path / "agent.toml"
        config_file.write_text("""
[agent]
name = "test"
description = "Test"

[prompts]
system = "Test"
""")

        agent = PlatformAgent.from_toml(config_file)
        ctx = WorkflowContext(secrets=Mock())

        mock_ai = Mock()
        mock_ai.generate = Mock(return_value="Custom analysis")
        ctx.ai = mock_ai

        git_status = create_mock_git_status(modified=["file.py"])
        ctx.data = {"git_status": git_status}

        result = agent.run(
            ctx,
            user_context="Focus on security issues",
            mode="analysis"
        )

        assert isinstance(result, Success)
        # Verify custom context was used in prompt
        call_args = mock_ai.generate.call_args
        assert "Focus on security issues" in call_args.kwargs["prompt"]

    def test_handles_git_diff_in_context(self, tmp_path):
        """Should include git diff in analysis if available."""
        config_file = tmp_path / "agent.toml"
        config_file.write_text("""
[agent]
name = "test"
description = "Test"

[prompts]
system = "Test"
""")

        agent = PlatformAgent.from_toml(config_file)
        ctx = WorkflowContext(secrets=Mock())

        mock_ai = Mock()
        mock_ai.generate = Mock(return_value="Analyzed diff")
        ctx.ai = mock_ai

        git_status = create_mock_git_status(modified=["file.py"])
        ctx.data = {
            "git_status": git_status,
            "git_diff": "diff --git a/file.py..."
        }

        result = agent.run(ctx, mode="analysis")

        assert isinstance(result, Success)
        # Verify diff was included in prompt
        call_args = mock_ai.generate.call_args
        assert "diff --git" in call_args.kwargs["prompt"]

    def test_error_on_ai_failure(self, tmp_path):
        """Should return Error if AI generation fails."""
        config_file = tmp_path / "agent.toml"
        config_file.write_text("""
[agent]
name = "test"
description = "Test"

[prompts]
system = "Test"
""")

        agent = PlatformAgent.from_toml(config_file)
        ctx = WorkflowContext(secrets=Mock())

        mock_ai = Mock()
        mock_ai.generate = Mock(side_effect=Exception("AI error"))
        ctx.ai = mock_ai

        git_status = create_mock_git_status(modified=["file.py"])
        ctx.data = {"git_status": git_status}

        result = agent.run(ctx, mode="analysis")

        assert isinstance(result, Error)
        assert "AI error" in result.message


class TestPlatformAgentInteractiveMode:
    """Tests for PlatformAgent in interactive mode."""

    def test_interactive_mode_returns_error_in_this_branch(self, tmp_path):
        """Interactive mode should return error (TAP not available in feat/workflow)."""
        config_file = tmp_path / "agent.toml"
        config_file.write_text("""
[agent]
name = "test"
description = "Test"

[prompts]
system = "Test"
""")

        agent = PlatformAgent.from_toml(config_file)
        ctx = WorkflowContext(secrets=Mock())
        ctx.ai = Mock()

        result = agent.run(ctx, mode="interactive")

        assert isinstance(result, Error)
        assert "TAP" in result.message or "interactive" in result.message.lower()


class TestPlatformAgentPrompts:
    """Tests for prompt handling."""

    def test_uses_analysis_system_prompt_if_available(self, tmp_path):
        """Should use analysis_system prompt in analysis mode."""
        config_file = tmp_path / "agent.toml"
        config_file.write_text("""
[agent]
name = "test"
description = "Test"

[prompts]
system = "Regular prompt"
analysis_system = "Analysis-specific prompt"
""")

        agent = PlatformAgent.from_toml(config_file)
        ctx = WorkflowContext(secrets=Mock())

        mock_ai = Mock()
        mock_ai.generate = Mock(return_value="Result")
        ctx.ai = mock_ai

        git_status = create_mock_git_status(modified=["file.py"])
        ctx.data = {"git_status": git_status}

        agent.run(ctx, mode="analysis")

        # Verify analysis_system prompt was used
        call_args = mock_ai.generate.call_args
        assert "Analysis-specific" in call_args.kwargs["system_prompt"]

    def test_falls_back_to_system_prompt_if_no_analysis_prompt(self, tmp_path):
        """Should fall back to regular system prompt if no analysis_system."""
        config_file = tmp_path / "agent.toml"
        config_file.write_text("""
[agent]
name = "test"
description = "Test"

[prompts]
system = "Regular prompt"
""")

        agent = PlatformAgent.from_toml(config_file)
        ctx = WorkflowContext(secrets=Mock())

        mock_ai = Mock()
        mock_ai.generate = Mock(return_value="Result")
        ctx.ai = mock_ai

        git_status = create_mock_git_status(modified=["file.py"])
        ctx.data = {"git_status": git_status}

        agent.run(ctx, mode="analysis")

        # Verify regular system prompt was used
        call_args = mock_ai.generate.call_args
        assert "Regular prompt" in call_args.kwargs["system_prompt"]
