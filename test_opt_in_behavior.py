#!/usr/bin/env python3
"""
Test script to verify AI opt-in behavior in GitHub PR workflow.
"""
import sys
from pathlib import Path

# Add plugin to path
plugin_path = Path(__file__).parent / "plugins" / "titan-plugin-github"
sys.path.insert(0, str(plugin_path))

from unittest.mock import Mock
from titan_cli.engine import WorkflowContext
from titan_plugin_github.steps.ai_pr_step import ai_suggest_pr_description


def create_mock_git_status(is_clean=False, modified=None, untracked=None):
    """Helper to create a properly mocked git status."""
    mock = Mock()
    mock.is_clean = is_clean
    mock.modified_files = modified or []
    mock.untracked_files = untracked or []
    return mock


def test_ai_not_used_by_default():
    """Test 1: AI should NOT run when use_ai is not set (default behavior)."""
    print("\n=== Test 1: Default Behavior (use_ai not set) ===")

    ctx = WorkflowContext(secrets=Mock())
    ctx.ai = Mock()  # AI is configured

    git_status = create_mock_git_status(modified=["test.py"])
    ctx.data = {
        "git_status": git_status,
        "current_branch": "feature/test",
        "base_branch": "main"
        # Note: use_ai is NOT set
    }

    result = ai_suggest_pr_description(ctx)

    print(f"Result type: {result.__class__.__name__}")
    print(f"Message: {result.message}")

    # Should skip because use_ai defaults to false
    assert result.__class__.__name__ == "Skip", "Should skip when use_ai not set"
    assert "use_ai=false" in result.message, "Message should mention use_ai=false"
    print("✓ PASSED: AI correctly skipped by default\n")
    return True


def test_ai_not_used_when_explicitly_false():
    """Test 2: AI should NOT run when use_ai=false."""
    print("=== Test 2: Explicit use_ai=false ===")

    ctx = WorkflowContext(secrets=Mock())
    ctx.ai = Mock()  # AI is configured

    git_status = create_mock_git_status(modified=["test.py"])
    ctx.data = {
        "git_status": git_status,
        "current_branch": "feature/test",
        "base_branch": "main",
        "use_ai": False  # Explicitly set to false
    }

    result = ai_suggest_pr_description(ctx)

    print(f"Result type: {result.__class__.__name__}")
    print(f"Message: {result.message}")

    # Should skip because use_ai is explicitly false
    assert result.__class__.__name__ == "Skip", "Should skip when use_ai=false"
    assert "use_ai=false" in result.message, "Message should mention use_ai=false"
    print("✓ PASSED: AI correctly skipped when explicitly disabled\n")
    return True


def test_ai_used_when_opted_in():
    """Test 3: AI should run when use_ai=true (opt-in)."""
    print("=== Test 3: Opt-in with use_ai=true ===")

    ctx = WorkflowContext(secrets=Mock())

    # Mock AI with proper response
    mock_ai = Mock()
    mock_ai.generate = Mock(return_value="TITLE: feat: test feature\n\nDESCRIPTION:\nTest description")
    ctx.ai = mock_ai

    # Mock UI
    ctx.ui = Mock()
    ctx.views = Mock()
    ctx.views.prompts.ask_confirm = Mock(return_value=True)

    git_status = create_mock_git_status(modified=["test.py"])
    ctx.data = {
        "git_status": git_status,
        "current_branch": "feature/test",
        "base_branch": "main",
        "use_ai": True  # Explicitly opt-in
    }

    result = ai_suggest_pr_description(ctx)

    print(f"Result type: {result.__class__.__name__}")
    print(f"Message: {result.message}")

    # Should succeed because use_ai=true
    assert result.__class__.__name__ == "Success", "Should succeed when use_ai=true"
    assert mock_ai.generate.called, "AI should be called when opted-in"
    print("✓ PASSED: AI correctly executed when opted-in\n")
    return True


def test_ai_skips_when_not_configured():
    """Test 4: AI should skip when use_ai=true but AI not configured."""
    print("=== Test 4: AI not configured (even with use_ai=true) ===")

    ctx = WorkflowContext(secrets=Mock())
    ctx.ai = None  # AI NOT configured

    git_status = create_mock_git_status(modified=["test.py"])
    ctx.data = {
        "git_status": git_status,
        "current_branch": "feature/test",
        "base_branch": "main",
        "use_ai": True  # Opted in, but AI not configured
    }

    result = ai_suggest_pr_description(ctx)

    print(f"Result type: {result.__class__.__name__}")
    print(f"Message: {result.message}")

    # Should skip because AI not configured
    assert result.__class__.__name__ == "Skip", "Should skip when AI not configured"
    assert "AI not configured" in result.message, "Message should mention AI not configured"
    print("✓ PASSED: AI correctly skipped when not configured\n")
    return True


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Testing AI Opt-In Behavior for GitHub PR Workflow")
    print("="*60)

    tests = [
        test_ai_not_used_by_default,
        test_ai_not_used_when_explicitly_false,
        test_ai_used_when_opted_in,
        test_ai_skips_when_not_configured,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}\n")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}\n")
            failed += 1

    print("="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)

    if failed == 0:
        print("\n🎉 All tests passed! AI is now properly opt-in.")
        print("\nDefault behavior: Deterministic (manual prompts)")
        print("With use_ai=true: AI-powered (requires AI configuration)")
    else:
        print(f"\n❌ {failed} test(s) failed")
        exit(1)
