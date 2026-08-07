# plugins/titan-plugin-git/titan_plugin_git/clients/services/merge_service.py
"""
Merge Service

Business logic for Git merge operations, including conflicted merges.
Uses network layer to execute commands and derives the merge state from the
repository itself rather than from git's (localized) output text.
"""
from typing import List

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError
from titan_cli.core.logging import log_client_operation

from ..network import GitNetwork
from ...models.view.merge import UIMergeResult
from ...operations.merge_operations import classify_merge_result
from ...exceptions import GitError


class MergeService:
    """
    Service for Git merge operations.

    Handles merging refs, inspecting conflicts, and finishing or aborting a
    merge that stopped with conflicts.
    """

    def __init__(self, git_network: GitNetwork):
        """
        Initialize Merge service.

        Args:
            git_network: GitNetwork instance for command execution
        """
        self.git = git_network

    @log_client_operation()
    def merge(
        self,
        ref: str,
        target_branch: str = "",
        no_ff: bool = False,
    ) -> ClientResult[UIMergeResult]:
        """
        Merge a ref into the current branch.

        A conflicted merge is NOT an error: it returns ClientSuccess with a
        CONFLICTED result so the caller can drive conflict resolution.

        Args:
            ref: Ref to merge (e.g. "origin/develop")
            target_branch: Branch receiving the merge (for display only)
            no_ff: Force a merge commit even when a fast-forward is possible

        Returns:
            ClientResult[UIMergeResult]
        """
        args = ["git", "merge", "--no-edit"]
        if no_ff:
            args.append("--no-ff")
        args.append(ref)

        try:
            head_before = self._head_sha()
            # check=False: a conflicted merge exits non-zero but is a valid outcome
            output = self.git.run_command(args, check=False)
            head_after = self._head_sha()
            has_second_parent = bool(
                self.git.run_command(
                    ["git", "rev-parse", "-q", "--verify", "HEAD^2"],
                    check=False
                ).strip()
            )
        except GitError as e:
            return ClientError(error_message=str(e), error_code="MERGE_ERROR")

        conflicts_result = self.get_conflicted_files()
        match conflicts_result:
            case ClientSuccess(data=conflicted_files):
                pass
            case ClientError() as err:
                return err

        in_progress_result = self.is_merge_in_progress()
        match in_progress_result:
            case ClientSuccess(data=merge_in_progress):
                pass
            case ClientError() as err:
                return err

        status = classify_merge_result(
            head_before=head_before,
            head_after=head_after,
            has_second_parent=has_second_parent,
            conflicted_files=conflicted_files,
            merge_in_progress=merge_in_progress,
        )

        result = UIMergeResult(
            status=status,
            source_ref=ref,
            target_branch=target_branch,
            conflicted_files=conflicted_files,
            raw_output=output,
        )

        return ClientSuccess(data=result, message=f"Merge finished with status '{status.value}'")

    def _head_sha(self) -> str:
        """Resolve HEAD without raising on an empty repository."""
        return self.git.run_command(["git", "rev-parse", "HEAD"], check=False).strip()

    @log_client_operation()
    def get_conflicted_files(self) -> ClientResult[List[str]]:
        """
        List paths with unresolved conflicts.

        Returns:
            ClientResult[List[str]] with unmerged paths (empty when none)
        """
        try:
            output = self.git.run_command(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                check=False
            )
            files = [line.strip() for line in output.splitlines() if line.strip()]
            return ClientSuccess(data=files, message=f"{len(files)} conflicted files")
        except GitError as e:
            return ClientError(error_message=str(e), error_code="CONFLICT_CHECK_ERROR")

    @log_client_operation()
    def is_merge_in_progress(self) -> ClientResult[bool]:
        """
        Check whether a merge is currently in progress (MERGE_HEAD exists).

        Returns:
            ClientResult[bool]
        """
        try:
            output = self.git.run_command(
                ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"],
                check=False
            )
            in_progress = bool(output.strip())
            return ClientSuccess(
                data=in_progress,
                message=f"Merge {'in progress' if in_progress else 'not in progress'}"
            )
        except GitError as e:
            return ClientError(error_message=str(e), error_code="MERGE_STATE_ERROR")

    @log_client_operation()
    def stage_all(self) -> ClientResult[None]:
        """
        Stage every change in the working tree (git add --all).

        Returns:
            ClientResult[None]
        """
        try:
            self.git.run_command(["git", "add", "--all"])
            return ClientSuccess(data=None, message="All changes staged")
        except GitError as e:
            return ClientError(error_message=str(e), error_code="STAGE_ERROR")

    @log_client_operation()
    def continue_merge(self) -> ClientResult[str]:
        """
        Complete an in-progress merge using git's suggested message.

        Uses `git commit --no-edit` rather than `git merge --continue` because
        the latter opens an editor, and the network layer cannot override
        GIT_EDITOR. Both commit the prepared MERGE_MSG.

        Returns:
            ClientResult[str] with the merge commit SHA
        """
        try:
            self.git.run_command(["git", "commit", "--no-edit"])
            sha = self.git.run_command(["git", "rev-parse", "HEAD"])
            return ClientSuccess(data=sha, message=f"Merge committed: {sha[:8]}")
        except GitError as e:
            return ClientError(error_message=str(e), error_code="MERGE_CONTINUE_ERROR")

    @log_client_operation()
    def abort_merge(self) -> ClientResult[None]:
        """
        Abort an in-progress merge and restore the pre-merge state.

        Returns:
            ClientResult[None]
        """
        try:
            self.git.run_command(["git", "merge", "--abort"])
            return ClientSuccess(data=None, message="Merge aborted")
        except GitError as e:
            return ClientError(error_message=str(e), error_code="MERGE_ABORT_ERROR")
