# plugins/titan-plugin-git/titan_plugin_git/clients/git_client_new.py
"""
Git Client Facade

Unified API that delegates to specialized services.
All methods return ClientResult for consistent error handling.
"""
from typing import List, Optional, Tuple

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError

from .network import GitNetwork
from .services import (
    BranchService,
    CommitService,
    StatusService,
    DiffService,
    RemoteService,
    StashService,
    TagService,
    WorktreeService,
)
from ..models.view import (
    UIGitBranch,
    UIGitCommit,
    UIGitStatus,
    UIGitTag,
    UIGitWorktree,
)
from ..messages import msg


class GitClient:
    """
    Git client facade - delegates to specialized services.

    All public methods return ClientResult[T] for consistent error handling.
    Uses pattern matching (match/case) for result handling in operations and steps.

    Examples:
        >>> client = GitClient()
        >>> result = client.get_current_branch()
        >>> match result:
        ...     case ClientSuccess(data=branch):
        ...         print(f"Current branch: {branch}")
        ...     case ClientError(error_message=err):
        ...         print(f"Error: {err}")
    """

    def __init__(
        self,
        repo_path: str = ".",
        main_branch: str = "main",
        default_remote: str = "origin"
    ):
        """
        Initialize Git client.

        Args:
            repo_path: Path to git repository (default: current directory)
            main_branch: Main branch name (from config)
            default_remote: Default remote name (from config)
        """
        self.repo_path = repo_path
        self.main_branch = main_branch
        self.default_remote = default_remote

        # Initialize network layer
        self.network = GitNetwork(repo_path=repo_path)

        # Initialize services
        self.branch_service = BranchService(self.network)
        self.commit_service = CommitService(self.network, main_branch, default_remote)
        self.status_service = StatusService(self.network)
        self.diff_service = DiffService(self.network, default_remote)
        self.remote_service = RemoteService(self.network)
        self.stash_service = StashService(self.network)
        self.tag_service = TagService(self.network)
        self.worktree_service = WorktreeService(self.network)

        # State for safe_checkout / return_to_original_branch
        self._original_branch: Optional[str] = None

    # ===== Branch Methods =====

    def get_current_branch(self) -> ClientResult[str]:
        """Get current branch name."""
        return self.branch_service.get_current_branch()

    def get_branches(self, remote: bool = False) -> ClientResult[List[UIGitBranch]]:
        """List branches."""
        return self.branch_service.get_branches(remote=remote)

    def create_branch(
        self, branch_name: str, start_point: str = "HEAD"
    ) -> ClientResult[None]:
        """Create a new branch."""
        return self.branch_service.create_branch(branch_name, start_point)

    def delete_branch(self, branch: str, force: bool = False) -> ClientResult[None]:
        """Delete a branch."""
        return self.branch_service.delete_branch(branch, force)

    def safe_delete_branch(self, branch: str, force: bool = False) -> ClientResult[None]:
        """Delete branch if not protected."""
        if self.is_protected_branch(branch):
            return ClientError(
                error_message=msg.Git.BRANCH_PROTECTED.format(branch=branch),
                error_code="BRANCH_PROTECTED"
            )
        return self.branch_service.delete_branch(branch, force)

    def checkout(self, branch: str) -> ClientResult[None]:
        """Checkout a branch."""
        return self.branch_service.checkout(branch)

    def branch_exists_on_remote(
        self, branch: str, remote: str = "origin"
    ) -> ClientResult[bool]:
        """Check if a branch exists on remote."""
        return self.branch_service.branch_exists_on_remote(branch, remote)

    def update_branch(
        self, branch: str, remote: Optional[str] = None
    ) -> ClientResult[None]:
        """
        Update branch from remote (fetch + merge --ff-only).

        Args:
            branch: Branch to update
            remote: Remote name (defaults to configured default_remote)

        Returns:
            ClientResult[None]
        """
        remote = remote or self.default_remote

        # Get current branch
        current_result = self.get_current_branch()
        match current_result:
            case ClientSuccess(data=current):
                pass
            case ClientError() as err:
                return err

        # Checkout target branch if needed
        if current != branch:
            checkout_result = self.checkout(branch)
            match checkout_result:
                case ClientError() as err:
                    return err
                case _:
                    pass

        # Fetch
        fetch_result = self.remote_service.fetch(remote, branch)
        match fetch_result:
            case ClientError() as err:
                return err
            case _:
                pass

        # Merge --ff-only
        try:
            self.network.run_command(["git", "merge", "--ff-only", f"{remote}/{branch}"])
        except Exception as e:
            error_str = str(e)
            if "merge conflict" in error_str.lower():
                return ClientError(
                    error_message=msg.Git.MERGE_CONFLICT_WHILE_UPDATING.format(branch=branch),
                    error_code="MERGE_CONFLICT"
                )
            return ClientError(error_message=error_str, error_code="MERGE_ERROR")

        # Return to original branch if needed
        if current != branch:
            return self.checkout(current)

        return ClientSuccess(data=None, message=f"Branch '{branch}' updated")

    def update_from_main(self) -> ClientResult[None]:
        """Update current branch from the configured main branch."""
        return self.update_branch(self.main_branch, self.default_remote)

    def safe_checkout(self, branch: str, auto_stash: bool = True) -> ClientResult[None]:
        """
        Safely checkout a branch with optional auto-stashing.

        Args:
            branch: Branch to checkout
            auto_stash: Automatically stash uncommitted changes

        Returns:
            ClientResult[None]
        """
        # Save current branch
        current_result = self.get_current_branch()
        match current_result:
            case ClientSuccess(data=current):
                self._original_branch = current
            case ClientError() as err:
                return err

        # Check for uncommitted changes
        has_changes_result = self.status_service.has_uncommitted_changes()
        match has_changes_result:
            case ClientSuccess(data=has_changes):
                pass
            case ClientError() as err:
                return err

        # Stash if needed
        if has_changes and auto_stash:
            stash_result = self.stash_service.stash_push()
            match stash_result:
                case ClientError() as err:
                    return err
                case _:
                    pass

        # Checkout
        return self.checkout(branch)

    def return_to_original_branch(self) -> ClientResult[None]:
        """Return to the original branch saved by safe_checkout."""
        if not self._original_branch:
            return ClientSuccess(data=None, message="No original branch to return to")

        checkout_result = self.checkout(self._original_branch)
        self._original_branch = None
        return checkout_result

    def is_protected_branch(self, branch: str) -> bool:
        """Check if a branch is protected (main, master, develop, etc.)."""
        protected = ["main", "master", "develop", "staging", "production"]
        return branch in protected

    # ===== Commit Methods =====

    def commit(
        self, message: str, all: bool = False, no_verify: bool = True
    ) -> ClientResult[str]:
        """Create a commit."""
        return self.commit_service.commit(message, all, no_verify)

    def commit_files(
        self, files: list, message: str, no_verify: bool = True
    ) -> ClientResult[str]:
        """Create a commit with specific files only."""
        return self.commit_service.commit_files(files, message, no_verify)

    def get_current_commit(self) -> ClientResult[str]:
        """Get current commit SHA (HEAD)."""
        return self.commit_service.get_current_commit()

    def get_commit_sha(self, ref: str) -> ClientResult[str]:
        """Get commit SHA for any git ref."""
        return self.commit_service.get_commit_sha(ref)

    def get_commits_vs_base(self) -> ClientResult[List[str]]:
        """Get commit messages from base branch to HEAD."""
        return self.commit_service.get_commits_vs_base()

    def get_branch_commits(
        self, base_branch: str, head_branch: str
    ) -> ClientResult[List[str]]:
        """Get list of commits in head_branch that are not in base_branch."""
        return self.commit_service.get_branch_commits(base_branch, head_branch)

    def get_commits_between_refs(
        self, base_ref: str, head_ref: str = "HEAD"
    ) -> ClientResult[List[str]]:
        """Get list of commits reachable from head_ref but not base_ref."""
        return self.commit_service.get_commits_between_refs(base_ref, head_ref)

    def count_commits_ahead(self, base_branch: str = "develop") -> ClientResult[int]:
        """Count how many commits current branch is ahead of base branch."""
        return self.commit_service.count_commits_ahead(base_branch)

    def count_unpushed_commits(
        self, branch: Optional[str] = None, remote: str = "origin"
    ) -> ClientResult[int]:
        """Count how many commits are unpushed to remote."""
        return self.commit_service.count_unpushed_commits(branch, remote)

    # ===== Status Methods =====

    def get_status(self) -> ClientResult[UIGitStatus]:
        """Get repository status."""
        return self.status_service.get_status()

    def has_uncommitted_changes(self) -> ClientResult[bool]:
        """Check if repository has uncommitted changes."""
        return self.status_service.has_uncommitted_changes()

    # ===== Diff Methods =====

    def get_diff(self, base_ref: str, head_ref: str = "HEAD") -> ClientResult[str]:
        """Get diff between two references."""
        return self.diff_service.get_diff(base_ref, head_ref)

    def get_uncommitted_diff(self) -> ClientResult[str]:
        """Get diff of all uncommitted changes."""
        return self.diff_service.get_uncommitted_diff()

    def get_uncommitted_diff_for_files(self, files: list[str]) -> ClientResult[str]:
        """Get diff of uncommitted changes limited to specific files."""
        return self.diff_service.get_uncommitted_diff_for_files(files)

    def get_staged_diff(self) -> ClientResult[str]:
        """Get diff of staged changes only."""
        return self.diff_service.get_staged_diff()

    def get_unstaged_diff(self) -> ClientResult[str]:
        """Get diff of unstaged changes only."""
        return self.diff_service.get_unstaged_diff()

    def get_file_diff(self, file_path: str) -> ClientResult[str]:
        """Get diff for a specific file."""
        return self.diff_service.get_file_diff(file_path)

    def get_branch_diff(self, base_branch: str, head_branch: str, context_lines: int = 3, use_remote: bool = False) -> ClientResult[str]:
        """
        Get diff between two branches.

        Args:
            base_branch: Base branch name
            head_branch: Head branch name
            context_lines: Number of context lines (default: 3)
            use_remote: If True, both branches are treated as remote refs (default: False)

        Returns:
            ClientResult[str] with diff output
        """
        return self.diff_service.get_branch_diff(base_branch, head_branch, context_lines, use_remote)

    def get_diff_stat(self, base_ref: str, head_ref: str = "HEAD") -> ClientResult[str]:
        """Get diff stat summary."""
        return self.diff_service.get_diff_stat(base_ref, head_ref)

    def get_uncommitted_diff_stat(self) -> ClientResult[str]:
        """Get diff stat summary of uncommitted changes."""
        return self.diff_service.get_uncommitted_diff_stat()

    def get_branch_diff_stat(
        self, base_branch: str, head_branch: str
    ) -> ClientResult[str]:
        """Get diff stat summary between two branches."""
        return self.diff_service.get_diff_stat(
            f"{self.default_remote}/{base_branch}",
            head_branch
        )

    # ===== Remote Methods =====

    def push(
        self,
        remote: str = "origin",
        branch: Optional[str] = None,
        set_upstream: bool = False,
        tags: bool = False
    ) -> ClientResult[None]:
        """Push to remote."""
        return self.remote_service.push(remote, branch, set_upstream, tags)

    def push_tag(self, tag_name: str, remote: str = "origin") -> ClientResult[None]:
        """Push a specific tag to remote."""
        return self.remote_service.push_tag(tag_name, remote)

    def pull(
        self, remote: str = "origin", branch: Optional[str] = None
    ) -> ClientResult[None]:
        """Pull from remote."""
        return self.remote_service.pull(remote, branch)

    def fetch(
        self,
        remote: str = "origin",
        branch: Optional[str] = None,
        all: bool = False
    ) -> ClientResult[None]:
        """Fetch from remote."""
        return self.remote_service.fetch(remote, branch, all)

    def fetch_refspec(self, remote: str, refspec: str) -> ClientResult[None]:
        """Fetch an explicit refspec from remote."""
        return self.remote_service.fetch_refspec(remote, refspec)

    def get_github_repo_info(self) -> ClientResult[Tuple[Optional[str], Optional[str]]]:
        """Extract GitHub repository owner and name from origin."""
        return self.remote_service.get_github_repo_info()

    # ===== Stash Methods =====

    def stash_push(self, message: Optional[str] = None) -> ClientResult[bool]:
        """Stash uncommitted changes."""
        return self.stash_service.stash_push(message)

    def stash_pop(self, stash_ref: Optional[str] = None) -> ClientResult[bool]:
        """Pop stash (apply and remove)."""
        return self.stash_service.stash_pop(stash_ref)

    def find_stash_by_message(self, message: str) -> ClientResult[Optional[str]]:
        """Find stash by message."""
        return self.stash_service.find_stash_by_message(message)

    def restore_stash(self, message: str) -> ClientResult[bool]:
        """Restore stash by finding it with a message and popping it."""
        return self.stash_service.restore_stash(message)

    # ===== Tag Methods =====

    def create_tag(
        self, tag_name: str, message: str, ref: str = "HEAD"
    ) -> ClientResult[None]:
        """Create an annotated tag."""
        return self.tag_service.create_tag(tag_name, message, ref)

    def delete_tag(self, tag_name: str) -> ClientResult[None]:
        """Delete a local tag."""
        return self.tag_service.delete_tag(tag_name)

    def tag_exists(self, tag_name: str) -> ClientResult[bool]:
        """Check if a tag exists locally."""
        return self.tag_service.tag_exists(tag_name)

    def remote_tag_exists(self, tag_name: str, remote: str = "origin") -> ClientResult[bool]:
        """Check if a tag exists on a remote."""
        return self.tag_service.remote_tag_exists(tag_name, remote)

    def list_tags(self) -> ClientResult[List[UIGitTag]]:
        """List all tags in the repository."""
        return self.tag_service.list_tags()

    # ===== Worktree Methods =====

    def create_worktree(
        self, path: str, branch: str, create_branch: bool = False, detached: bool = False
    ) -> ClientResult[None]:
        """Create a new worktree."""
        return self.worktree_service.create_worktree(path, branch, create_branch, detached)

    def remove_worktree(self, path: str, force: bool = False) -> ClientResult[None]:
        """Remove a worktree."""
        return self.worktree_service.remove_worktree(path, force)

    def prune_worktrees(self) -> ClientResult[None]:
        """Prune stale worktree metadata for directories that no longer exist."""
        return self.worktree_service.prune_worktrees()

    def list_worktrees(self) -> ClientResult[List[UIGitWorktree]]:
        """List all worktrees."""
        return self.worktree_service.list_worktrees()

    def run_in_worktree(self, worktree_path: str, args: List[str]) -> ClientResult[str]:
        """Run a git command in a specific worktree."""
        return self.worktree_service.run_in_worktree(worktree_path, args)

    def get_commits(self, worktree_path: str, limit: int = 10) -> ClientResult[List[UIGitCommit]]:
        """Get recent commits from a worktree."""
        return self.worktree_service.get_commits(worktree_path, limit)

    def get_worktree_diff_stat(self, worktree_path: str) -> ClientResult[str]:
        """Get diff stat of uncommitted changes in a worktree."""
        return self.worktree_service.get_diff_stat_in_worktree(worktree_path)

    def checkout_branch_in_worktree(
        self, worktree_path: str, branch_name: str, force: bool = False
    ) -> ClientResult[None]:
        """Checkout (or create) a branch in a worktree."""
        return self.worktree_service.checkout_branch_in_worktree(worktree_path, branch_name, force)

    def commit_in_worktree(
        self,
        worktree_path: str,
        message: str,
        add_all: bool = True,
        no_verify: bool = False
    ) -> ClientResult[str]:
        """Stage and commit changes in a worktree."""
        return self.worktree_service.commit_in_worktree(worktree_path, message, add_all, no_verify)

    def push_from_worktree(
        self, worktree_path: str, branch: str, remote: Optional[str] = None
    ) -> ClientResult[None]:
        """Push commits from a worktree to remote."""
        remote = remote or self.default_remote
        return self.worktree_service.push_from_worktree(worktree_path, branch, remote)
