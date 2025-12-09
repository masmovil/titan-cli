#!/usr/bin/env python3
"""
Test script to manually execute the create-pr workflow with AI opt-in.

This simulates running: titan workflow run create-pr --param use_ai=true
"""
import sys
from pathlib import Path
from unittest.mock import Mock
from titan_cli.core.config import TitanConfig
from titan_cli.core.secrets import SecretManager
from titan_cli.engine import WorkflowContext


def test_workflow_with_ai_enabled():
    """Test create-pr workflow with use_ai=true."""
    print("\n" + "="*70)
    print("TEST: Create PR Workflow with AI Enabled (use_ai=true)")
    print("="*70)

    # Load config
    config = TitanConfig()
    secrets = SecretManager()

    # Create context
    ctx = WorkflowContext(secrets=secrets)

    # Mock UI for testing
    ctx.ui = Mock()
    ctx.ui.text = Mock()
    ctx.ui.text.styled_text = Mock()
    ctx.ui.text.body = Mock()
    ctx.ui.text.info = Mock()
    ctx.ui.text.warning = Mock()
    ctx.ui.text.subtitle = Mock()
    ctx.ui.spacer = Mock()
    ctx.ui.spacer.small = Mock()
    ctx.ui.panel = Mock()
    ctx.ui.panel.render = Mock()

    ctx.views = Mock()
    ctx.views.prompts = Mock()
    ctx.views.prompts.ask_confirm = Mock(return_value=True)
    ctx.views.prompts.ask_text = Mock(return_value="Test PR Title")

    # Mock git status with changes
    git_status = Mock()
    git_status.is_clean = False
    git_status.modified_files = ["test.py", "README.md"]
    git_status.untracked_files = []
    git_status.branch = "feat/test-workflow"

    # Set up context data with AI ENABLED
    ctx.data = {
        "use_ai": True,  # OPT-IN TO AI
        "git_status": git_status,
        "current_branch": "feat/test-workflow",
        "base_branch": "main"
    }

    # Mock AI
    if not ctx.ai:
        print("\n⚠ AI not configured, using mock AI")
        ctx.ai = Mock()
        ctx.ai.generate = Mock(return_value="TITLE: feat: test workflow execution\n\nDESCRIPTION:\nTest description for PR")

    # Check workflow file exists
    workflow_path = Path("plugins/titan-plugin-github/titan_plugin_github/workflows/create-pr.yaml")
    if not workflow_path.exists():
        print(f"\n❌ Workflow not found: {workflow_path}")
        return False

    print(f"\n✓ Found workflow: {workflow_path}")

    try:
        # Import the AI step to test it directly
        from titan_plugin_github.steps.ai_pr_step import ai_suggest_pr_description

        print("\n1. Testing AI step directly with use_ai=True...")
        result = ai_suggest_pr_description(ctx)

        print(f"   Result type: {result.__class__.__name__}")
        print(f"   Message: {result.message}")

        if result.__class__.__name__ == "Success":
            print("   ✓ AI step executed successfully!")
            if "pr_title" in result.metadata:
                print(f"   PR Title: {result.metadata['pr_title']}")
            if "pr_body" in result.metadata:
                print(f"   PR Body: {result.metadata['pr_body'][:100]}...")
            return True
        elif result.__class__.__name__ == "Skip":
            print(f"   ✗ AI step was skipped: {result.message}")
            return False
        else:
            print(f"   ✗ AI step failed: {result.message}")
            return False

    except Exception as e:
        print(f"\n❌ Error executing workflow: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_workflow_with_ai_disabled():
    """Test create-pr workflow with use_ai=false (default)."""
    print("\n" + "="*70)
    print("TEST: Create PR Workflow with AI Disabled (use_ai=false, default)")
    print("="*70)

    # Load config
    config = TitanConfig()
    secrets = SecretManager()

    # Create context
    ctx = WorkflowContext(secrets=secrets)

    # Mock UI
    ctx.ui = Mock()

    # Mock git status with changes
    git_status = Mock()
    git_status.is_clean = False
    git_status.modified_files = ["test.py"]
    git_status.untracked_files = []

    # Set up context data with AI DISABLED (default)
    ctx.data = {
        "use_ai": False,  # DEFAULT DETERMINISTIC BEHAVIOR
        "git_status": git_status,
        "current_branch": "feat/test-workflow",
        "base_branch": "main"
    }

    # Mock AI (even though it's configured, it shouldn't be called)
    ctx.ai = Mock()
    ctx.ai.generate = Mock(return_value="This should NOT be called")

    try:
        # Import the AI step
        from titan_plugin_github.steps.ai_pr_step import ai_suggest_pr_description

        print("\n1. Testing AI step directly with use_ai=False...")
        result = ai_suggest_pr_description(ctx)

        print(f"   Result type: {result.__class__.__name__}")
        print(f"   Message: {result.message}")

        # Verify AI was NOT called
        if ctx.ai.generate.called:
            print("   ✗ ERROR: AI was called when use_ai=false!")
            return False

        if result.__class__.__name__ == "Skip" and "use_ai=false" in result.message:
            print("   ✓ AI step correctly skipped (deterministic behavior)!")
            return True
        else:
            print(f"   ✗ Unexpected result: {result}")
            return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Add plugin to path
    plugin_path = Path(__file__).parent / "plugins" / "titan-plugin-github"
    sys.path.insert(0, str(plugin_path))

    print("\n🧪 Testing Create PR Workflow - AI Opt-In Behavior")

    tests = [
        ("AI Disabled (Default)", test_workflow_with_ai_disabled),
        ("AI Enabled (Opt-In)", test_workflow_with_ai_enabled),
    ]

    passed = 0
    failed = 0

    for name, test in tests:
        try:
            if test():
                passed += 1
                print(f"\n✅ {name}: PASSED")
            else:
                failed += 1
                print(f"\n❌ {name}: FAILED")
        except Exception as e:
            failed += 1
            print(f"\n❌ {name}: ERROR - {e}")

    print("\n" + "="*70)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*70)

    if failed == 0:
        print("\n🎉 All tests passed! Workflow AI opt-in is working correctly.")
        print("\n📝 Summary:")
        print("   • use_ai=false (default): AI step skipped, deterministic behavior")
        print("   • use_ai=true (opt-in): AI step executes and generates PR description")
    else:
        print(f"\n❌ {failed} test(s) failed")
        sys.exit(1)
