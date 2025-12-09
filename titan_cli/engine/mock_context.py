"""
Mock Clients for Workflow Previews

Provides mock implementations of clients (Git, AI, GitHub) that can be used
by workflow previews to execute real step functions with fake data.

Each preview should create its own mock context with customized data.
"""

from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class MockGitStatus:
    """Mock git status for previews"""
    is_clean: bool = False
    modified_files: list = None
    untracked_files: list = None
    staged_files: list = None

    def __post_init__(self):
        if self.modified_files is None:
            self.modified_files = ["cli.py", "messages.py"]
        if self.untracked_files is None:
            self.untracked_files = ["preview.py"]
        if self.staged_files is None:
            self.staged_files = []


class MockGitClient:
    """Mock GitClient for previews"""

    def __init__(self):
        self.main_branch = "master"
        self.current_branch = "feat/workflow-preview"
        self.default_remote = "origin"

    def get_status(self):
        return MockGitStatus(is_clean=False)

    def get_current_branch(self) -> str:
        return self.current_branch

    def branch_exists_on_remote(self, branch: str, remote: str = "origin") -> bool:
        # Mock: always return False to trigger set_upstream
        return False

    def get_uncommitted_diff(self) -> str:
        return """diff --git a/cli.py b/cli.py
index abc123..def456 100644
--- a/cli.py
+++ b/cli.py
@@ -1,3 +1,5 @@
+from titan_cli.preview import preview_workflow
+
 def main():
-    pass
+    # Added preview functionality
+    preview_workflow()"""

    def get_branch_diff(self, base: str, head: str) -> str:
        return """diff --git a/preview.py b/preview.py
new file mode 100644
index 0000000..abc123
--- /dev/null
+++ b/preview.py
@@ -0,0 +1,50 @@
+# Preview system for workflows
+def preview_workflow(name):
+    pass"""

    def get_branch_commits(self, base: str, head: str) -> list[str]:
        return [
            "feat(workflows): add preview system",
            "feat(ui): improve panel rendering",
            "fix(git): handle uncommitted changes"
        ]

    def commit(self, message: str, all: bool = True) -> str:
        return "abc1234567890"

    def push(self, remote: str = "origin", branch: Optional[str] = None, set_upstream: bool = False):
        return True


class MockAIResponse:
    """Mock AI response"""
    def __init__(self, content: str):
        self.content = content


class MockAIClient:
    """Mock AIClient for previews"""

    def is_available(self) -> bool:
        return True

    def generate(self, messages, max_tokens: int = 1000, temperature: float = 0.7):
        # Extract the prompt
        prompt = messages[0].content if messages else ""

        # Generate different responses based on context
        if "commit message" in prompt.lower():
            return MockAIResponse(
                "feat(workflows): add preview system for workflows with mocked data"
            )
        elif "pull request" in prompt.lower() or "pr" in prompt.lower():
            return MockAIResponse("""TITLE: feat(workflows): Add preview system for testing workflow UI

DESCRIPTION:
## Summary
- Added `titan preview workflow <name>` command
- Created mock context system for workflow previews
- Implemented preview for create-pr-ai workflow

## Type of Change
- [x] New feature (non-breaking)
- [ ] Bug fix
- [ ] Breaking change

## Testing
- [x] Tested preview command with create-pr-ai
- [x] Verified mocked data displays correctly""")
        else:
            return MockAIResponse("Mocked AI response")


class MockGitHubClient:
    """Mock GitHubClient for previews"""

    def __init__(self):
        self.repo_owner = "mockuser"
        self.repo_name = "mock-repo"

    def create_pull_request(self, title: str, body: str, head: str, base: str, draft: bool = False):
        """Mock create PR - returns fake PR data"""
        return {
            "number": 123,
            "url": "https://github.com/mockuser/mock-repo/pull/123",
            "title": title,
            "body": body,
            "head": head,
            "base": base,
            "draft": draft
        }


class MockSecretManager:
    """Mock SecretManager for previews"""

    def __init__(self, project_path=None):
        self.project_path = project_path

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Mock get secret - returns fake values"""
        mock_secrets = {
            "github_token": "ghp_mocktoken123",
            "anthropic_api_key": "sk-ant-mock123",
        }
        return mock_secrets.get(key, default)

    def set(self, key: str, value: str) -> None:
        """Mock set secret - does nothing"""
        pass


# Export all mock classes for use in previews
__all__ = [
    "MockGitStatus",
    "MockGitClient",
    "MockAIResponse",
    "MockAIClient",
    "MockGitHubClient",
    "MockSecretManager",
]
