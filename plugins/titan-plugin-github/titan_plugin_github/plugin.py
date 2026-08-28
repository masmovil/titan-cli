# plugins/titan-plugin-github/titan_plugin_github/plugin.py
from pathlib import Path
from typing import Optional

from titan_cli.core.plugins.plugin_base import TitanPlugin
from titan_cli.core.config import TitanConfig
from titan_cli.core.security import SecretBroker
from titan_cli.core.plugins.models import GitHubPluginConfig
from .clients.github_client import GitHubClient
from .exceptions import GitHubError
from .managers import ChecklistManager, GitHubManagers, ReviewProfileManager


class GitHubPlugin(TitanPlugin):
    """
    Titan CLI Plugin for GitHub operations.
    """

    @property
    def titan_requires(self) -> str:
        # Must stay in sync with the titan-cli dependency in this plugin's
        # pyproject.toml; a repo test enforces the pairing.
        return ">=0.8.0"

    @property
    def name(self) -> str:
        return "github"

    @property
    def description(self) -> str:
        return "Provides GitHub integration for PRs, issues, and more."

    @property
    def dependencies(self) -> list[str]:
        return ["git"]

    def initialize(self, config: TitanConfig, broker: SecretBroker) -> None:
        """
        Initializes the GitHubClient.
        """
        # Get plugin-specific configuration data
        plugin_config_data = self._get_plugin_config(config)

        # Validate configuration using Pydantic model
        validated_config = GitHubPluginConfig(**plugin_config_data)

        repo_owner = validated_config.repo_owner
        repo_name = validated_config.repo_name

        # Get the git client from the registry
        git_plugin = config.registry.get_plugin("git")
        if not git_plugin or not git_plugin.is_available():
            raise GitHubError("The 'git' plugin is a required dependency and is not available.")
        git_client = git_plugin.get_client()

        # Attempt to auto-detect if not explicitly configured
        if not repo_owner or not repo_name:
            detected_owner, detected_name = git_client.get_github_repo_info()
            if detected_owner and detected_name:
                repo_owner = repo_owner or detected_owner
                repo_name = repo_name or detected_name

        # If still missing, raise an error
        if not repo_owner or not repo_name:
            raise GitHubError("GitHub repository owner and name must be configured or auto-detected from git remote.")

        # Load PR template if configured
        pr_template = None
        template_path = validated_config.pr_template_path or ".github/pull_request_template.md"
        template_file = Path(template_path)
        if template_file.exists() and template_file.is_file():
            try:
                pr_template = template_file.read_text(encoding="utf-8")
            except OSError:
                pass  # Template not found, use None

        # Initialize client with validated configuration and git_client
        self._client = GitHubClient(
            config=validated_config,
            git_client=git_client,
            repo_owner=repo_owner, # Pass detected/configured owner
            repo_name=repo_name, # Pass detected/configured name
            pr_template=pr_template # Pass loaded PR template
        )

    def _get_plugin_config(self, config: TitanConfig) -> dict:
        """
        Extract plugin-specific configuration.
        
        Args:
            config: TitanConfig instance
        
        Returns:
            Plugin config dict (empty if not configured)
        """
        if "github" not in config.config.plugins:
            return {}

        plugin_entry = config.config.plugins["github"]
        return plugin_entry.config if hasattr(plugin_entry, 'config') else {}

    def get_config_schema(self) -> dict:
        """Returns the JSON schema for the plugin's configuration."""
        return GitHubPluginConfig.model_json_schema()

    def is_available(self) -> bool:
        """
        Checks if the GitHub CLI is installed and available.
        """
        import shutil
        return shutil.which("gh") is not None and hasattr(self, '_client') and self._client is not None

    @property
    def workflows_path(self) -> Optional[Path]:
        """
        Returns the path to the workflows directory for this plugin.
        """
        return Path(__file__).parent / "workflows"

    def get_client(self) -> GitHubClient:
        """
        Returns the initialized GitHubClient instance.
        """
        # Ensure the client is initialized, potentially adding a check here
        if not hasattr(self, '_client') or self._client is None:
            raise GitHubError("GitHubPlugin not initialized. GitHub client may not be available.")
        return self._client

    def get_workflow_managers(self, project_root: Optional[Path] = None) -> GitHubManagers:
        """Return workflow-local managers for the GitHub plugin."""
        return GitHubManagers(
            checklist=ChecklistManager(project_root=project_root),
            review_profile=ReviewProfileManager(project_root=project_root),
        )

    def get_steps(self) -> dict:
        """
        Returns a dictionary of available workflow steps.
        """
        from .steps.create_pr_step import create_pr_step
        from .steps.github_prompt_steps import prompt_for_pr_title_step, prompt_for_pr_body_step, prompt_for_pr_draft_step, prompt_for_issue_body_step, prompt_for_self_assign_step, prompt_for_labels_step
        from .steps.ai_pr_step import ai_suggest_pr_description_step
        from .steps.issue_steps import ai_suggest_issue_title_and_body_step, create_issue_steps
        from .steps.preview_step import preview_and_confirm_issue_step
        from .steps.pull_request_steps import (
            get_pull_request_step,
            merge_pull_request_step,
            verify_pull_request_state_step,
        )
        from .steps.pr_review_steps import (
            select_pr_for_review_step,
            fetch_pending_comments_step,
            check_clean_state_step,
            checkout_pr_branch_step,
            review_comments_step,
            push_commits_step,
            send_comment_replies_step,
            request_review_step,
            checkout_original_branch_step,
        )
        from .steps.worktree_steps import (
            create_worktree_step,
            cleanup_worktree_step,
        )
        from .steps.code_review_steps import (
            select_pr_for_code_review,
            fetch_pr_review_bundle,
            build_change_manifest,
            build_existing_comments_index,
            classify_pr,
            score_review_candidates,
            build_review_checklist,
            select_review_strategy,
            ai_review_plan,
            validate_review_plan,
            resolve_review_context,
            ai_review_findings,
            normalize_findings,
            dedupe_findings,
            verify_findings,
            build_new_comment_actions,
            validate_review_actions,
            submit_review_actions,
            build_thread_review_candidates,
            build_thread_review_contexts,
            ai_thread_resolution,
            normalize_thread_decisions,
            build_thread_actions,
        )
        from .steps.release_steps import select_release_step
        return {
            "create_pr": create_pr_step,
            "prompt_for_pr_title": prompt_for_pr_title_step,
            "prompt_for_pr_body": prompt_for_pr_body_step,
            "prompt_for_pr_draft": prompt_for_pr_draft_step,
            "prompt_for_issue_body_step": prompt_for_issue_body_step,
            "prompt_for_self_assign": prompt_for_self_assign_step,
            "prompt_for_labels": prompt_for_labels_step,
            "ai_suggest_pr_description": ai_suggest_pr_description_step,
            "ai_suggest_issue_title_and_body": ai_suggest_issue_title_and_body_step,
            "create_issue": create_issue_steps,
            "preview_and_confirm_issue": preview_and_confirm_issue_step,
            "get_pull_request": get_pull_request_step,
            "merge_pull_request": merge_pull_request_step,
            "verify_pull_request_state": verify_pull_request_state_step,
            "select_pr_for_review": select_pr_for_review_step,
            "fetch_pending_comments": fetch_pending_comments_step,
            "check_clean_state": check_clean_state_step,
            "checkout_pr_branch": checkout_pr_branch_step,
            "review_comments": review_comments_step,
            "push_commits": push_commits_step,
            "send_comment_replies": send_comment_replies_step,
            "request_review": request_review_step,
            "checkout_original_branch": checkout_original_branch_step,
            "create_worktree": create_worktree_step,
            "cleanup_worktree": cleanup_worktree_step,
            # Code review steps
            "select_pr_for_code_review": select_pr_for_code_review,
            "fetch_pr_review_bundle": fetch_pr_review_bundle,
            # Releases
            "select_release": select_release_step,
            # Phase 2: cheap context steps (pre-AI)
            "build_change_manifest": build_change_manifest,
            "build_existing_comments_index": build_existing_comments_index,
            "classify_pr": classify_pr,
            "score_review_candidates": score_review_candidates,
            "build_review_checklist": build_review_checklist,
            "select_review_strategy": select_review_strategy,
            # Phase 3: directed AI analysis (first AI call)
            "ai_review_plan": ai_review_plan,
            "validate_review_plan": validate_review_plan,
            "resolve_review_context": resolve_review_context,
            # Phase 4: targeted review (second AI call)
            "ai_review_findings": ai_review_findings,
            "normalize_findings": normalize_findings,
            "dedupe_findings": dedupe_findings,
            "verify_findings": verify_findings,
            # Phase 5: UI + submit
            "build_new_comment_actions": build_new_comment_actions,
            "validate_review_actions": validate_review_actions,
            "submit_review_actions": submit_review_actions,
            # Phase 6: thread resolution
            "build_thread_review_candidates": build_thread_review_candidates,
            "build_thread_review_contexts": build_thread_review_contexts,
            "ai_thread_resolution": ai_thread_resolution,
            "normalize_thread_decisions": normalize_thread_decisions,
            "build_thread_actions": build_thread_actions,
        }
