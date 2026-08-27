# plugins/titan-plugin-git/titan_plugin_git/clients/services/commit_service.py
"""
Commit Service

Business logic for Git commit operations.
Uses network layer to execute commands, parses to network models, maps to view models.
"""
import os
from typing import List, Optional, Sequence

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError
from titan_cli.core.logging import log_client_operation

from ..network import GitNetwork
from ...exceptions import GitCommandError


class CommitService:
    """
    Service for Git commit operations.

    Handles creating commits, fetching commit info, and commit history.
    Returns view models ready for UI rendering.
    """

    def __init__(self, git_network: GitNetwork, main_branch: str = "main", default_remote: str = "origin"):
        """
        Initialize Commit service.

        Args:
            git_network: GitNetwork instance for command execution
            main_branch: Main branch name (from config)
            default_remote: Default remote name (from config)
        """
        self.git = git_network
        self.main_branch = main_branch
        self.default_remote = default_remote

    @log_client_operation()
    def commit(
        self, message: str, all: bool = False, no_verify: bool = True
    ) -> ClientResult[str]:
        """
        Create a commit.

        Args:
            message: Commit message
            all: Stage all modified and new files
            no_verify: Skip pre-commit and commit-msg hooks

        Returns:
            ClientResult[str] with commit hash
        """
        try:
            if all:
                self.git.run_command(["git", "add", "--all"])

            args = ["git", "commit", "-m", message]
            if no_verify:
                args.append("--no-verify")
            self.git.run_command(args)

            # Get the commit hash
            commit_hash = self.git.run_command(["git", "rev-parse", "HEAD"])

            return ClientSuccess(
                data=commit_hash,
                message=f"Commit created: {commit_hash[:7]}"
            )

        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="COMMIT_ERROR")

    @log_client_operation()
    def commit_files(
        self, files: Sequence[str], message: str, no_verify: bool = True
    ) -> ClientResult[str]:
        """
        Create a commit with specific files only.

        Args:
            files: File paths to stage and commit
            message: Commit message
            no_verify: Skip pre-commit and commit-msg hooks

        Returns:
            ClientResult[str] with commit hash
        """
        try:
            # Separate existing files from deleted ones
            # Only include files that exist in the filesystem OR are tracked in git
            existing_files = []
            deleted_files = []

            for f in files:
                if os.path.exists(f):
                    # File exists in filesystem
                    existing_files.append(f)
                else:
                    # File doesn't exist - check if it's tracked in git
                    # If it's tracked, we can use git rm; if not, skip it
                    try:
                        self.git.run_command(["git", "ls-files", "--error-unmatch", f])
                        # File is tracked, mark for deletion
                        deleted_files.append(f)
                    except GitCommandError:
                        # File not tracked in git, skip it
                        pass

            # Stage existing files with git add
            if existing_files:
                self.git.run_command(["git", "add", "--"] + existing_files)

            # Stage deleted files with git rm
            if deleted_files:
                self.git.run_command(["git", "rm", "--"] + deleted_files)

            args = ["git", "commit", "-m", message]
            if no_verify:
                args.append("--no-verify")
            args.extend(["--"] + list(files))
            self.git.run_command(args)

            commit_hash = self.git.run_command(["git", "rev-parse", "HEAD"])
            return ClientSuccess(
                data=commit_hash,
                message=f"Commit created: {commit_hash[:7]}"
            )
        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="COMMIT_ERROR")

    @log_client_operation()
    def get_current_commit(self) -> ClientResult[str]:
        """
        Get current commit SHA (HEAD).

        Returns:
            ClientResult[str] with full SHA of current commit
        """
        try:
            commit_hash = self.git.run_command(["git", "rev-parse", "HEAD"])
            return ClientSuccess(
                data=commit_hash,
                message=f"Current commit: {commit_hash[:7]}"
            )
        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="COMMIT_ERROR")

    @log_client_operation()
    def get_commit_sha(self, ref: str) -> ClientResult[str]:
        """
        Get commit SHA for any git ref.

        Args:
            ref: Git reference (e.g., "HEAD", "develop", "origin/main", "v1.0.0")

        Returns:
            ClientResult[str] with full SHA of the commit
        """
        try:
            commit_hash = self.git.run_command(["git", "rev-parse", ref])
            return ClientSuccess(
                data=commit_hash,
                message=f"Commit SHA for {ref}: {commit_hash[:7]}"
            )
        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="COMMIT_ERROR")

    @log_client_operation()
    def get_commits_vs_base(self) -> ClientResult[List[str]]:
        """
        Get commit messages from base branch to HEAD.

        Returns:
            ClientResult[List[str]] with commit messages
        """
        try:
            result = self.git.run_command([
                "git", "log", "--oneline",
                f"{self.main_branch}..HEAD",
                "--pretty=format:%s"
            ])

            if not result:
                return ClientSuccess(data=[], message="No commits ahead of base")

            commits = [line.strip() for line in result.split('\n') if line.strip()]
            return ClientSuccess(
                data=commits,
                message=f"Found {len(commits)} commits ahead of {self.main_branch}"
            )

        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="COMMIT_ERROR")

    @log_client_operation()
    def get_branch_commits(
        self, base_branch: str, head_branch: str
    ) -> ClientResult[List[str]]:
        """
        Get list of commits in head_branch that are not in base_branch.

        Args:
            base_branch: Base branch name
            head_branch: Head branch name

        Returns:
            ClientResult[List[str]] with commit messages
        """
        try:
            output = self.git.run_command([
                "git", "log",
                f"{self.default_remote}/{base_branch}..{head_branch}",
                "--pretty=format:%s"
            ])

            if not output:
                return ClientSuccess(data=[], message="No commits found")

            commits = [line.strip() for line in output.split('\n') if line.strip()]
            return ClientSuccess(
                data=commits,
                message=f"Found {len(commits)} commits"
            )

        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="COMMIT_ERROR")

    @log_client_operation()
    def get_commits_between_refs(
        self, base_ref: str, head_ref: str = "HEAD"
    ) -> ClientResult[List[str]]:
        """
        Get list of commit subjects reachable from head_ref but not base_ref.

        Args:
            base_ref: Base git reference (tag, branch, or commit SHA)
            head_ref: Head git reference (default: HEAD)

        Returns:
            ClientResult[List[str]] with commit messages
        """
        try:
            output = self.git.run_command([
                "git", "log", f"{base_ref}..{head_ref}", "--pretty=format:%s"
            ])

            if not output:
                return ClientSuccess(data=[], message="No commits found")

            commits = [line.strip() for line in output.split("\n") if line.strip()]
            return ClientSuccess(
                data=commits,
                message=f"Found {len(commits)} commits between {base_ref} and {head_ref}",
            )

        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="COMMIT_ERROR")

    @log_client_operation()
    def count_commits_ahead(self, base_branch: str = "develop") -> ClientResult[int]:
        """
        Count how many commits current branch is ahead of base branch.

        Args:
            base_branch: Base branch to compare against

        Returns:
            ClientResult[int] with number of commits ahead
        """
        try:
            result = self.git.run_command([
                "git", "rev-list", "--count", f"{base_branch}..HEAD"
            ])
            count = int(result.strip())
            return ClientSuccess(
                data=count,
                message=f"{count} commits ahead of {base_branch}"
            )
        except (GitCommandError, ValueError) as e:
            return ClientError(error_message=str(e), error_code="COMMIT_COUNT_ERROR")

    @log_client_operation()
    def count_unpushed_commits(
        self, branch: Optional[str] = None, remote: str = "origin"
    ) -> ClientResult[int]:
        """
        Count how many commits are unpushed to remote.

        Args:
            branch: Branch name (default: current branch)
            remote: Remote name (default: "origin")

        Returns:
            ClientResult[int] with number of unpushed commits
        """
        try:
            if branch is None:
                branch = self.git.run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])

            result = self.git.run_command([
                "git", "rev-list", "--count", f"{remote}/{branch}..{branch}"
            ], check=False)

            count = int(result.strip()) if result else 0
            return ClientSuccess(
                data=count,
                message=f"{count} unpushed commits"
            )

        except (GitCommandError, ValueError) as e:
            return ClientError(error_message=str(e), error_code="COMMIT_COUNT_ERROR")
