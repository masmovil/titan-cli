# plugins/titan-plugin-git/titan_plugin_git/clients/services/diff_service.py
"""
Diff Service

Business logic for Git diff operations.
Uses network layer to execute commands and returns diff outputs.
"""
from typing import List

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError
from titan_cli.core.logging import log_client_operation

from ..network import GitNetwork
from ...exceptions import GitCommandError, GitError
from ...models.view import UIFileChurn


class DiffService:
    """
    Service for Git diff operations.

    Handles getting diffs between references, branches, files, and states.
    Returns raw diff output as strings.
    """

    def __init__(self, git_network: GitNetwork, default_remote: str = "origin"):
        """
        Initialize Diff service.

        Args:
            git_network: GitNetwork instance for command execution
            default_remote: Default remote name (from config)
        """
        self.git = git_network
        self.default_remote = default_remote

    @log_client_operation()
    def get_diff(self, base_ref: str, head_ref: str = "HEAD") -> ClientResult[str]:
        """
        Get diff between two references.

        Args:
            base_ref: Base reference (branch, commit, tag)
            head_ref: Head reference (default: "HEAD")

        Returns:
            ClientResult[str] with diff output
        """
        try:
            diff = self.git.run_command(
                ["git", "diff", f"{base_ref}...{head_ref}"],
                check=False
            )
            return ClientSuccess(data=diff, message="Diff retrieved")
        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="DIFF_ERROR")

    @log_client_operation()
    def get_uncommitted_diff(self) -> ClientResult[str]:
        """
        Get diff of all uncommitted changes (staged + unstaged + untracked).

        Uses git add --intent-to-add to make untracked files visible.

        Returns:
            ClientResult[str] with diff output
        """
        try:
            # Add untracked files to index without staging content
            self.git.run_command(["git", "add", "--intent-to-add", "."], check=False)

            # git diff HEAD shows all changes vs last commit
            diff = self.git.run_command(["git", "diff", "HEAD"], check=False)
            return ClientSuccess(data=diff, message="Uncommitted diff retrieved")
        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="DIFF_ERROR")

    @log_client_operation()
    def get_uncommitted_diff_for_files(self, files: list[str]) -> ClientResult[str]:
        """
        Get diff of uncommitted changes limited to the provided file paths.

        Uses git add --intent-to-add on the selected paths so untracked files are
        visible in the diff without fully staging their content.

        Args:
            files: File paths to include in the diff

        Returns:
            ClientResult[str] with diff output
        """
        try:
            if not files:
                return self.get_uncommitted_diff()

            self.git.run_command(["git", "add", "--intent-to-add", "--"] + files, check=False)
            diff = self.git.run_command(["git", "diff", "HEAD", "--"] + files, check=False)
            return ClientSuccess(data=diff, message="Filtered uncommitted diff retrieved")
        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="DIFF_ERROR")

    @log_client_operation()
    def get_staged_diff(self) -> ClientResult[str]:
        """
        Get diff of staged changes only (index vs HEAD).

        Returns:
            ClientResult[str] with diff output
        """
        try:
            diff = self.git.run_command(["git", "diff", "--cached"], check=False)
            return ClientSuccess(data=diff, message="Staged diff retrieved")
        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="DIFF_ERROR")

    @log_client_operation()
    def get_unstaged_diff(self) -> ClientResult[str]:
        """
        Get diff of unstaged changes only (working directory vs index).

        Returns:
            ClientResult[str] with diff output
        """
        try:
            diff = self.git.run_command(["git", "diff"], check=False)
            return ClientSuccess(data=diff, message="Unstaged diff retrieved")
        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="DIFF_ERROR")

    @log_client_operation()
    def get_uncommitted_diff_stat(self) -> ClientResult[str]:
        """
        Get diff stat summary of uncommitted changes (working tree vs HEAD).

        Shows summary of files changed, insertions, and deletions.

        Returns:
            ClientResult[str] with diff stat output
        """
        try:
            # Add untracked files to index without staging content
            self.git.run_command(["git", "add", "--intent-to-add", "."], check=False)

            # git diff --stat=300 HEAD shows all changes vs last commit (300 prevents path truncation with ...)
            diff_stat = self.git.run_command(["git", "diff", "--stat=300", "HEAD"], check=False)
            return ClientSuccess(data=diff_stat, message="Uncommitted diff stat retrieved")
        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="DIFF_ERROR")

    @log_client_operation()
    def get_file_diff(self, file_path: str) -> ClientResult[str]:
        """
        Get diff for a specific file.

        Args:
            file_path: Path to the file

        Returns:
            ClientResult[str] with diff output
        """
        try:
            diff = self.git.run_command(
                ["git", "diff", "HEAD", "--", file_path],
                check=False
            )
            return ClientSuccess(data=diff, message=f"Diff for {file_path} retrieved")
        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="DIFF_ERROR")

    @log_client_operation()
    def get_branch_diff(self, base_branch: str, head_branch: str, context_lines: int = 3, use_remote: bool = False) -> ClientResult[str]:
        """
        Get diff between two branches.

        Args:
            base_branch: Base branch name
            head_branch: Head branch name
            context_lines: Number of unchanged context lines around each change (default: 3).
                When called from code review with context_lines=20, provides extended context
                for AI analysis. The higher value gives better code understanding for review
                quality, while still keeping token usage reasonable compared to reading entire files.
            use_remote: If True, both branches are prefixed with the configured default_remote.
                Used for PR reviews where branches are remote refs only (not checked out locally).

        Returns:
            ClientResult[str] with diff output
        """
        try:
            # Build branch references using configured default_remote if use_remote=True
            if use_remote:
                base_ref = f"{self.default_remote}/{base_branch}"
                head_ref = f"{self.default_remote}/{head_branch}"
            else:
                base_ref = f"{self.default_remote}/{base_branch}"
                head_ref = head_branch

            diff = self.git.run_command(
                ["git", "diff", f"-U{context_lines}", f"{base_ref}...{head_ref}"],
                check=False
            )
            return ClientSuccess(
                data=diff,
                message=f"Diff between {base_branch} and {head_branch} retrieved"
            )
        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="DIFF_ERROR")

    @log_client_operation()
    def get_branch_numstat(
        self, base_branch: str, head_branch: str, use_remote: bool = False
    ) -> ClientResult[List[UIFileChurn]]:
        """
        Get per-file addition/deletion counters between two branches.

        Args:
            base_branch: Base branch name
            head_branch: Head branch name
            use_remote: If True, both branches are prefixed with the configured
                default_remote. Used for PR reviews where branches are remote
                refs only (not checked out locally).

        Returns:
            ClientResult[List[UIFileChurn]] with one entry per changed file.
            Binary files are included with is_binary=True and zero counters.
        """
        try:
            if use_remote:
                base_ref = f"{self.default_remote}/{base_branch}"
                head_ref = f"{self.default_remote}/{head_branch}"
            else:
                base_ref = f"{self.default_remote}/{base_branch}"
                head_ref = head_branch

            # --no-renames keeps the output one plain "add<TAB>del<TAB>path" line
            # per file: a rename becomes delete+add, so the current path always
            # appears with its full counters and no "old => new" forms to parse.
            output = self.git.run_command(
                ["git", "diff", "--numstat", "--no-renames", f"{base_ref}...{head_ref}"],
                check=False,
            )

            churns: List[UIFileChurn] = []
            for line in output.splitlines():
                parts = line.split("\t")
                if len(parts) != 3:
                    continue
                added, deleted, path = parts
                if added == "-" or deleted == "-":
                    churns.append(UIFileChurn(path=path, additions=0, deletions=0, is_binary=True))
                    continue
                churns.append(UIFileChurn(path=path, additions=int(added), deletions=int(deleted)))

            return ClientSuccess(
                data=churns,
                message=f"Numstat between {base_branch} and {head_branch} retrieved",
            )
        except (GitError, ValueError) as e:
            return ClientError(error_message=str(e), error_code="DIFF_ERROR")

    @log_client_operation()
    def get_changed_files(self, base_ref: str, head_ref: str) -> ClientResult[List[str]]:
        """
        List the paths that differ between two refs (commits, branches or tags).

        Uses --no-renames so a renamed file reports both its old and new path —
        callers checking whether a specific path was touched see either side.

        Args:
            base_ref: Base ref, used verbatim (no remote prefixing)
            head_ref: Head ref, used verbatim

        Returns:
            ClientResult[List[str]] with the changed paths
        """
        try:
            output = self.git.run_command(
                ["git", "diff", "--name-only", "--no-renames", base_ref, head_ref],
                check=False,
            )
            paths = [line.strip() for line in output.splitlines() if line.strip()]
            return ClientSuccess(
                data=paths,
                message=f"{len(paths)} file(s) differ between {base_ref} and {head_ref}",
            )
        except GitError as e:
            return ClientError(error_message=str(e), error_code="DIFF_ERROR")

    @log_client_operation()
    def get_diff_stat(self, base_ref: str, head_ref: str = "HEAD") -> ClientResult[str]:
        """
        Get diff stat summary between two references.

        Args:
            base_ref: Base reference
            head_ref: Head reference (default: "HEAD")

        Returns:
            ClientResult[str] with diff stat output
        """
        try:
            diff_stat = self.git.run_command(
                ["git", "diff", "--stat=300", f"{base_ref}...{head_ref}"],
                check=False
            )
            return ClientSuccess(data=diff_stat, message="Diff stat retrieved")
        except GitCommandError as e:
            return ClientError(error_message=str(e), error_code="DIFF_ERROR")
