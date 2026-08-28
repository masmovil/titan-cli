# plugins/titan-plugin-git/titan_plugin_git/clients/services/worktree_service.py
"""
Worktree Service

Business logic for Git worktree operations.
Uses network layer to execute commands, parses to network models, maps to view models.
"""
from typing import List

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError
from titan_cli.core.logging import log_client_operation

from ..network import GitNetwork
from ...models.network.worktree import NetworkGitWorktree
from ...models.network.commit import NetworkGitCommit
from ...models.view.worktree import UIGitWorktree
from ...models.view.commit import UIGitCommit
from ...models.mappers import from_network_worktree
from ...models.mappers.commit_mapper import from_network_commit
from ...exceptions import GitError


class WorktreeService:
    """
    Service for Git worktree operations.

    Handles creating, removing, listing, and running commands in worktrees.
    Returns view models ready for UI rendering.
    """

    def __init__(self, git_network: GitNetwork):
        """
        Initialize Worktree service.

        Args:
            git_network: GitNetwork instance for command execution
        """
        self.git = git_network

    @log_client_operation()
    def create_worktree(
        self,
        path: str,
        branch: str,
        create_branch: bool = False,
        detached: bool = False,
        start_point: str | None = None,
    ) -> ClientResult[None]:
        """
        Create a new worktree at the specified path.

        Args:
            path: Path where to create the worktree
            branch: Branch or ref to checkout in the worktree
            create_branch: If True, create the branch
            detached: If True, create in detached HEAD mode (allows using same branch as current repo)
            start_point: Optional ref used as the starting point for a newly created branch

        Returns:
            ClientResult[None]
        """
        try:
            args = ["git", "worktree", "add"]

            if detached:
                args.append("--detach")

            if create_branch:
                args.extend(["-b", branch])

            args.append(path)

            if create_branch and start_point:
                args.append(start_point)
            elif not create_branch:
                args.append(branch)

            self.git.run_command(args)
            return ClientSuccess(data=None, message=f"Worktree created at {path}")

        except GitError as e:
            return ClientError(error_message=str(e), error_code="WORKTREE_CREATE_ERROR")

    @log_client_operation()
    def remove_worktree(self, path: str, force: bool = False) -> ClientResult[None]:
        """
        Remove a worktree.

        Args:
            path: Path to the worktree to remove
            force: Force removal even if worktree is dirty

        Returns:
            ClientResult[None]
        """
        try:
            args = ["git", "worktree", "remove", path]

            if force:
                args.append("--force")

            self.git.run_command(args)
            return ClientSuccess(data=None, message=f"Worktree removed: {path}")

        except GitError as e:
            return ClientError(error_message=str(e), error_code="WORKTREE_REMOVE_ERROR")

    @log_client_operation()
    def prune_worktrees(self) -> ClientResult[None]:
        """
        Prune worktree administrative metadata for directories that no longer exist.

        Git keeps a record under ``.git/worktrees`` for every registered worktree. When
        the directory is deleted by hand (or a removal is interrupted), that record is
        left behind and ``git worktree add`` on the same path fails as "already
        registered", while ``git worktree remove`` fails as "not a working tree".
        Pruning clears those stale records so the path becomes reusable.

        Returns:
            ClientResult[None]
        """
        try:
            self.git.run_command(["git", "worktree", "prune"])
            return ClientSuccess(data=None, message="Pruned stale worktree metadata")

        except GitError as e:
            return ClientError(error_message=str(e), error_code="WORKTREE_PRUNE_ERROR")

    @log_client_operation()
    def list_worktrees(self) -> ClientResult[List[UIGitWorktree]]:
        """
        List all worktrees.

        Returns:
            ClientResult[List[UIGitWorktree]]
        """
        try:
            output = self.git.run_command(["git", "worktree", "list", "--porcelain"])

            network_worktrees = []
            current_worktree = {}

            for line in output.splitlines():
                line = line.strip()
                if not line:
                    if current_worktree:
                        # Create NetworkGitWorktree from parsed data
                        network_worktrees.append(NetworkGitWorktree(
                            path=current_worktree.get("path", ""),
                            branch=current_worktree.get("branch"),
                            commit=current_worktree.get("commit"),
                            is_bare=current_worktree.get("bare", False),
                            is_detached=current_worktree.get("detached", False)
                        ))
                        current_worktree = {}
                    continue

                if line.startswith("worktree "):
                    current_worktree["path"] = line.split("worktree ", 1)[1]
                elif line.startswith("HEAD "):
                    current_worktree["commit"] = line.split("HEAD ", 1)[1]
                elif line.startswith("branch "):
                    current_worktree["branch"] = line.split("branch ", 1)[1].replace("refs/heads/", "")
                elif line == "bare":
                    current_worktree["bare"] = True
                elif line == "detached":
                    current_worktree["detached"] = True

            # Handle last worktree if exists
            if current_worktree:
                network_worktrees.append(NetworkGitWorktree(
                    path=current_worktree.get("path", ""),
                    branch=current_worktree.get("branch"),
                    commit=current_worktree.get("commit"),
                    is_bare=current_worktree.get("bare", False),
                    is_detached=current_worktree.get("detached", False)
                ))

            # Map to UI models
            ui_worktrees = [from_network_worktree(wt) for wt in network_worktrees]

            return ClientSuccess(
                data=ui_worktrees,
                message=f"Found {len(ui_worktrees)} worktrees"
            )

        except GitError as e:
            return ClientError(error_message=str(e), error_code="WORKTREE_LIST_ERROR")

    @log_client_operation()
    def run_in_worktree(self, worktree_path: str, args: List[str]) -> ClientResult[str]:
        """
        Run a git command in a specific worktree.

        Args:
            worktree_path: Path to the worktree
            args: Command arguments (including 'git')

        Returns:
            ClientResult[str] with command stdout
        """
        try:
            # Use git -C <path> to run command in worktree
            if args[0] == "git":
                args = ["git", "-C", worktree_path] + args[1:]

            return ClientSuccess(
                data=self.git.run_command(args, cwd=worktree_path),
                message="Command executed in worktree"
            )

        except GitError as e:
            return ClientError(error_message=str(e), error_code="WORKTREE_COMMAND_ERROR")

    @log_client_operation()
    def get_commits(
        self, worktree_path: str, limit: int = 10
    ) -> ClientResult[List[UIGitCommit]]:
        """
        Get recent commits from a worktree.

        Args:
            worktree_path: Path to the worktree
            limit: Maximum number of commits to retrieve

        Returns:
            ClientResult[List[UIGitCommit]] with commit history
        """
        try:
            # Use custom format for easy parsing
            # Format: hash\nsubject\nauthor\ndate\n--END--
            format_str = "%H%n%s%n%an <%ae>%n%ad%n--END--"
            args = [
                "git", "-C", worktree_path,
                "log",
                f"--pretty=format:{format_str}",
                "--date=short",
                "-n", str(limit)
            ]

            output = self.git.run_command(args, cwd=worktree_path)

            # Parse commits
            network_commits = []
            lines = output.strip().split('\n')
            i = 0
            while i < len(lines):
                if i + 3 < len(lines):
                    commit_hash = lines[i].strip()
                    subject = lines[i + 1].strip()
                    author = lines[i + 2].strip()
                    date = lines[i + 3].strip()

                    network_commits.append(NetworkGitCommit(
                        hash=commit_hash,
                        message=subject,  # Just subject for now
                        author=author,
                        date=date
                    ))

                    # Skip to next commit (after --END--)
                    i += 5
                else:
                    break

            # Map to UI models
            ui_commits = [from_network_commit(c) for c in network_commits]

            return ClientSuccess(
                data=ui_commits,
                message=f"Retrieved {len(ui_commits)} commits"
            )

        except GitError as e:
            return ClientError(error_message=str(e), error_code="WORKTREE_COMMITS_ERROR")

    @log_client_operation()
    def get_diff_stat_in_worktree(self, worktree_path: str) -> ClientResult[str]:
        """
        Get diff stat of uncommitted changes in a worktree.

        Args:
            worktree_path: Path to the worktree

        Returns:
            ClientResult[str] with raw git diff --stat output
        """
        try:
            args = ["git", "-C", worktree_path, "diff", "--stat=300", "HEAD"]
            output = self.git.run_command(args, cwd=worktree_path)
            return ClientSuccess(data=output, message="Worktree diff stat retrieved")
        except GitError as e:
            return ClientError(error_message=str(e), error_code="WORKTREE_DIFF_STAT_ERROR")

    @log_client_operation()
    def checkout_branch_in_worktree(
        self,
        worktree_path: str,
        branch_name: str,
        force: bool = False
    ) -> ClientResult[None]:
        """
        Checkout (or create) a branch in a worktree.

        Args:
            worktree_path: Path to worktree
            branch_name: Branch name to checkout
            force: Use -B to force create/reset branch if it exists

        Returns:
            ClientResult[None]
        """
        try:
            flag = "-B" if force else "-b"
            self.git.run_command(
                ["git", "-C", worktree_path, "checkout", flag, branch_name],
                cwd=worktree_path
            )
            return ClientSuccess(data=None, message=f"Checked out branch '{branch_name}'")
        except GitError as e:
            return ClientError(error_message=str(e), error_code="WORKTREE_CHECKOUT_ERROR")

    @log_client_operation()
    def commit_in_worktree(
        self,
        worktree_path: str,
        message: str,
        add_all: bool = True,
        no_verify: bool = False
    ) -> ClientResult[str]:
        """
        Stage and commit changes in a worktree.

        Args:
            worktree_path: Path to worktree
            message: Commit message
            add_all: Stage all changes before committing
            no_verify: Skip pre-commit hooks

        Returns:
            ClientResult[str] with commit hash
        """
        try:
            if add_all:
                self.git.run_command(
                    ["git", "-C", worktree_path, "add", "--all"],
                    cwd=worktree_path
                )

            commit_args = ["git", "-C", worktree_path, "commit"]
            if no_verify:
                commit_args.append("--no-verify")
            commit_args.extend(["-m", message])

            self.git.run_command(commit_args, cwd=worktree_path)

            commit_hash = self.git.run_command(
                ["git", "-C", worktree_path, "rev-parse", "HEAD"],
                cwd=worktree_path
            )
            return ClientSuccess(data=commit_hash.strip(), message="Commit created")

        except GitError as e:
            return ClientError(error_message=str(e), error_code="WORKTREE_COMMIT_ERROR")

    @log_client_operation()
    def push_from_worktree(
        self, worktree_path: str, branch: str, remote: str = "origin"
    ) -> ClientResult[None]:
        """
        Push commits from a worktree to remote.

        Handles both regular and detached worktrees by using HEAD:branch syntax.
        This allows pushing even if the branch is checked out elsewhere.

        Args:
            worktree_path: Path to worktree
            branch: Branch name to push to
            remote: Remote name (default: "origin")

        Returns:
            ClientResult[None]
        """
        try:
            # Use HEAD:branch syntax to support detached worktrees
            args = ["git", "-C", worktree_path, "push", remote, f"HEAD:{branch}"]

            self.git.run_command(args, cwd=worktree_path)
            return ClientSuccess(
                data=None,
                message=f"Pushed to {remote}/{branch}"
            )

        except GitError as e:
            return ClientError(
                error_message=str(e),
                error_code="WORKTREE_PUSH_ERROR"
            )
