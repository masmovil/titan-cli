#!/usr/bin/env python3
"""
Test script to verify PlatformAgent integration with workflows.

This creates a simple workflow that:
1. Simulates git changes
2. Uses PlatformAgent to analyze them
3. Generates a commit message suggestion

Run with: poetry run python test_agent_workflow.py
"""

from pathlib import Path
from titan_cli.engine import WorkflowContext, Success, Error, Skip, is_success
from titan_cli.core.secrets import SecretManager
from titan_cli.agents.steps import (
    ai_analyze_changes_step,
    ai_suggest_commit_message_step,
    platform_agent_analysis_step,
    platform_agent_suggest_commit_step
)
from unittest.mock import Mock


def create_mock_git_status():
    """Create a mock git status with changes."""
    status = Mock()
    status.is_clean = False
    status.branch = "feat/test-agents"
    status.modified_files = [
        "titan_cli/agents/platform_agent.py",
        "titan_cli/agents/steps/platform_agent_step.py",
        "tests/agents/test_platform_agent.py"
    ]
    status.untracked_files = [
        "config/agents/platform_agent.toml",
        "docs/AGENT_STEPS.md"
    ]
    return status


def create_test_context():
    """Create a WorkflowContext with AI configured."""
    # Create context
    secrets = SecretManager()
    ctx = WorkflowContext(secrets=secrets)

    # Add mock git status
    git_status = create_mock_git_status()
    ctx.data["git_status"] = git_status

    # Add mock git diff (optional)
    ctx.data["git_diff"] = """
diff --git a/titan_cli/agents/platform_agent.py b/titan_cli/agents/platform_agent.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/titan_cli/agents/platform_agent.py
@@ -0,0 +1,100 @@
+class PlatformAgent:
+    def run(self, ctx, mode="analysis"):
+        # Agent implementation
+        pass
"""

    # Try to configure AI if available
    try:
        from titan_cli.core.config import TitanConfig
        from titan_cli.ai.client import AIClient

        config = TitanConfig.load()

        if hasattr(config, 'ai') and config.ai:
            print("✓ AI configured, will use real AI")
            ctx.ai = AIClient(config.ai)
        else:
            print("⚠ AI not configured, will use mock")
            ctx.ai = create_mock_ai()
    except Exception as e:
        print(f"⚠ Could not load AI config: {e}")
        print("⚠ Using mock AI instead")
        ctx.ai = create_mock_ai()

    return ctx


def create_mock_ai():
    """Create a mock AI client for testing without real API."""
    mock_ai = Mock()

    # Mock the generate method to return realistic responses
    def mock_generate(prompt, system_prompt=None, **kwargs):
        if "commit message" in prompt.lower():
            return "feat(agents): Add PlatformAgent with dual mode support"
        else:
            return """Analysis of changes:

- Added new PlatformAgent implementation
- Created workflow step wrappers for agent integration
- Comprehensive test coverage with 35 tests
- TOML-based configuration for consistency

This looks like a significant feature addition for AI agent integration."""

    mock_ai.generate = mock_generate
    mock_ai.chat = mock_generate  # Alias for compatibility

    return mock_ai


def test_generic_ai_steps():
    """Test generic AI steps (simple, hardcoded prompts)."""
    print("\n" + "="*70)
    print("TEST 1: Generic AI Steps")
    print("="*70)

    ctx = create_test_context()

    # Run steps manually
    print("\n1. Running ai_analyze_changes_step...")
    result1 = ai_analyze_changes_step(ctx)
    print(f"   Result: {result1.__class__.__name__} - {result1.message}")

    if isinstance(result1, Success) and "ai_analysis" in result1.metadata:
        ctx.data["ai_analysis"] = result1.metadata["ai_analysis"]
        print(f"\n📊 Analysis:")
        print(result1.metadata["ai_analysis"])

    print("\n2. Running ai_suggest_commit_message_step...")
    result2 = ai_suggest_commit_message_step(ctx)
    print(f"   Result: {result2.__class__.__name__} - {result2.message}")

    if isinstance(result2, Success) and "suggested_commit_message" in result2.metadata:
        print(f"\n💬 Suggested commit message:")
        print(f"  {result2.metadata['suggested_commit_message']}")

    return isinstance(result1, Success) and isinstance(result2, Success)


def test_platform_agent_steps():
    """Test PlatformAgent steps (TOML-configured)."""
    print("\n" + "="*70)
    print("TEST 2: PlatformAgent Steps")
    print("="*70)

    ctx = create_test_context()

    # Check if config exists
    config_path = Path("config/agents/platform_agent.toml")
    if not config_path.exists():
        print(f"\n⚠ Config not found: {config_path}")
        print("⚠ Skipping PlatformAgent test")
        return False

    print(f"✓ Found config: {config_path}")

    # Run steps manually
    print("\n1. Running platform_agent_analysis_step...")
    result1 = platform_agent_analysis_step(ctx)
    print(f"   Result: {result1.__class__.__name__} - {result1.message}")

    if isinstance(result1, Success) and "agent_analysis" in result1.metadata:
        ctx.data["agent_analysis"] = result1.metadata["agent_analysis"]
        print(f"\n📊 Agent analysis:")
        print(result1.metadata["agent_analysis"])

    print("\n2. Running platform_agent_suggest_commit_step...")
    result2 = platform_agent_suggest_commit_step(ctx)
    print(f"   Result: {result2.__class__.__name__} - {result2.message}")

    if isinstance(result2, Success) and "commit_message" in result2.metadata:
        print(f"\n💬 Agent suggested commit message:")
        print(f"  {result2.metadata['commit_message']}")

    return isinstance(result1, Success) and isinstance(result2, Success)


def main():
    """Run all tests."""
    print("\n🧪 Testing Agent Workflow Integration")
    print("="*70)

    try:
        # Test 1: Generic AI steps
        result1 = test_generic_ai_steps()

        # Test 2: PlatformAgent steps
        result2 = test_platform_agent_steps()

        # Summary
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"Generic AI Steps:     {'✓ PASS' if result1 else '✗ FAIL'}")
        print(f"PlatformAgent Steps:  {'✓ PASS' if result2 else '✗ FAIL'}")
        print("="*70)

        if result1 and result2:
            print("\n✓ All tests passed!")
            return 0
        else:
            print("\n✗ Some tests failed")
            return 1

    except Exception as e:
        print(f"\n✗ Error running tests: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
