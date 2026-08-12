# plugins/titan-plugin-git/titan_plugin_git/clients/network/git_network.py
"""
Git Network Client

Low-level git CLI command executor.
Handles subprocess execution and error handling.
No model conversion - returns raw command output strings.
"""
import subprocess
import shutil
import time
from typing import List, Optional

from titan_cli.core.logging.config import get_logger

from ...exceptions import (
    GitError,
    GitClientError,
    GitCommandError,
    GitNotRepositoryError
)
from ...messages import msg


class GitNetwork:
    """
    Git network client using git CLI.

    Executes git commands and handles errors.
    Returns raw command output (strings) without parsing or model conversion.

    Examples:
        >>> network = GitNetwork(repo_path=".")
        >>> output = network.run_command(["git", "status", "--short"])
        >>> # Returns raw git status output
    """

    def __init__(self, repo_path: str = "."):
        """
        Initialize Git network client.

        Args:
            repo_path: Path to git repository (default: current directory)

        Raises:
            GitClientError: If git CLI is not installed
            GitNotRepositoryError: If not in a git repository
        """
        self.repo_path = repo_path
        self._logger = get_logger(__name__)
        self._check_git_installed()
        self._check_repository()

    def _check_git_installed(self) -> None:
        """
        Check if git CLI is installed.

        Raises:
            GitClientError: If git is not found
        """
        if not shutil.which("git"):
            raise GitClientError(msg.Git.CLI_NOT_FOUND)

    def _check_repository(self) -> None:
        """
        Check if current directory is a git repository.

        Raises:
            GitNotRepositoryError: If not in a git repository
        """
        try:
            self.run_command(["git", "rev-parse", "--is-inside-work-tree"], check=False)
        except GitCommandError:
            raise GitNotRepositoryError(
                msg.Git.NOT_A_REPOSITORY.format(repo_path=self.repo_path)
            )

    def run_command(
        self,
        args: List[str],
        check: bool = True,
        cwd: Optional[str] = None,
        strip_output: bool = True
    ) -> str:
        """
        Run git command and return stdout.

        Args:
            args: Command arguments (including 'git')
            check: Raise exception on error (default: True)
            cwd: Optional working directory (overrides repo_path)
            strip_output: Strip surrounding whitespace from stdout (default: True).
                Pass False for diff output: a diff whose last hunk ends in an empty
                context line ends with a meaningful " \\n" that stripping destroys,
                leaving the hunk one line short of what its @@ header declares.

        Returns:
            Command stdout as string

        Raises:
            GitCommandError: If command fails
            GitNotRepositoryError: If not in a git repository
            GitClientError: If git CLI not found
            GitError: If unexpected error occurs

        Examples:
            >>> output = network.run_command(["git", "status", "--short"])
            >>> # Returns: "M file1.txt\\n?? file2.txt"
        """
        # Log only the subcommand — never args[2:] (may contain remote URLs, commit messages)
        subcommand = args[1] if len(args) > 1 else "unknown"
        start = time.time()

        try:
            result = subprocess.run(
                args,
                cwd=cwd or self.repo_path,
                capture_output=True,
                text=True,
                check=check
            )
            self._logger.debug(
                "git_command_ok",
                subcommand=subcommand,
                duration=round(time.time() - start, 3),
            )
            return result.stdout.rstrip() if strip_output else result.stdout
        except subprocess.CalledProcessError as e:
            self._logger.debug(
                "git_command_failed",
                subcommand=subcommand,
                duration=round(time.time() - start, 3),
                exit_code=e.returncode,
            )
            error_msg = e.stderr.strip() if e.stderr else str(e)
            if "not a git repository" in error_msg:
                raise GitNotRepositoryError(
                    msg.Git.NOT_A_REPOSITORY.format(repo_path=self.repo_path)
                )
            raise GitCommandError(
                msg.Git.COMMAND_FAILED.format(error_msg=error_msg)
            ) from e
        except FileNotFoundError:
            raise GitClientError(msg.Git.CLI_NOT_FOUND)
        except Exception as e:
            raise GitError(msg.Git.UNEXPECTED_ERROR.format(e=e)) from e

    def get_repo_path(self) -> str:
        """
        Get configured repository path.

        Returns:
            Repository path string
        """
        return self.repo_path
