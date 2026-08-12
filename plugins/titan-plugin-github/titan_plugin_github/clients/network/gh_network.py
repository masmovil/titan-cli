# plugins/titan-plugin-github/titan_plugin_github/clients/network/gh_network.py
"""
GitHub REST Network Client

Low-level gh CLI command executor.
Handles subprocess execution, authentication, and error handling.
No model conversion - returns raw JSON strings/dicts.
"""
import subprocess
import time
from typing import List, Optional

from titan_cli.core.logging.config import get_logger

from ...exceptions import GitHubError, GitHubAuthenticationError, GitHubAPIError
from ...messages import msg


class GHNetwork:
    """
    GitHub REST network client using gh CLI.

    Executes gh CLI commands and handles errors.
    Returns raw command output (strings) without parsing or model conversion.

    Examples:
        >>> network = GHNetwork(repo_owner="acme", repo_name="project")
        >>> output = network.run_command(["pr", "view", "123", "--json", "title"])
        >>> # Returns raw JSON string
    """

    def __init__(self, repo_owner: str, repo_name: str):
        """
        Initialize GH network client.

        Args:
            repo_owner: GitHub repository owner
            repo_name: GitHub repository name

        Raises:
            GitHubAuthenticationError: If gh CLI is not authenticated
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self._logger = get_logger(__name__)
        self.check_auth()

    def check_auth(self) -> None:
        """
        Check if gh CLI is authenticated.

        Raises:
            GitHubAuthenticationError: If not authenticated
        """
        try:
            subprocess.run(["gh", "auth", "status"], capture_output=True, check=True)
        except subprocess.CalledProcessError:
            raise GitHubAuthenticationError(msg.GitHub.NOT_AUTHENTICATED)

    def run_command(
        self, args: List[str], stdin_input: Optional[str] = None, strip_output: bool = True
    ) -> str:
        """
        Run gh CLI command and return stdout.

        Args:
            args: Command arguments (without 'gh' prefix)
            stdin_input: Optional input to pass via stdin (for multiline text)
            strip_output: Strip surrounding whitespace from stdout (default: True).
                Pass False for diff output: a diff whose last hunk ends in an empty
                context line ends with a meaningful " \\n" that stripping destroys,
                leaving the hunk one line short of what its @@ header declares.

        Returns:
            Command stdout as string

        Raises:
            GitHubAPIError: If command fails
            GitHubError: If gh CLI not found or unexpected error

        Examples:
            >>> output = network.run_command(["pr", "view", "123", "--json", "title"])
            >>> # Returns: '{"title": "My PR"}'
        """
        # Log only subcommand + action — never args[2:] (may contain PR body, issue content)
        subcommand = args[0] if args else "unknown"
        action = args[1] if len(args) > 1 else ""
        start = time.time()

        try:
            result = subprocess.run(
                ["gh"] + args,
                input=stdin_input,
                capture_output=True,
                text=True,
                check=True,
            )
            self._logger.debug(
                "gh_command_ok",
                subcommand=subcommand,
                action=action,
                duration=round(time.time() - start, 3),
            )
            return result.stdout.strip() if strip_output else result.stdout
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.strip() if e.stderr else ""
            stdout = e.stdout.strip() if e.stdout else ""
            self._logger.error(
                "gh_command_failed",
                subcommand=subcommand,
                action=action,
                duration=round(time.time() - start, 3),
                exit_code=e.returncode,
                stderr_preview=stderr[:500],
                stdout_preview=stdout[:500],
            )
            error_parts = []
            if stderr:
                error_parts.append(stderr)
            if stdout:
                error_parts.append(stdout)
            if not error_parts:
                error_parts.append(str(e))
            error_msg = " | ".join(error_parts)
            raise GitHubAPIError(
                msg.GitHub.API_ERROR.format(error_msg=error_msg),
                stderr=stderr or None,
                stdout=stdout or None,
                exit_code=e.returncode,
            ) from e
        except FileNotFoundError:
            raise GitHubError(msg.GitHub.CLI_NOT_FOUND)
        except Exception as e:
            raise GitHubError(msg.GitHub.UNEXPECTED_ERROR.format(error=e))

    def get_repo_arg(self) -> List[str]:
        """
        Get --repo argument for gh commands.

        Returns:
            List with --repo flag and value, or empty list if no repo configured
        """
        if self.repo_owner and self.repo_name:
            return ["--repo", f"{self.repo_owner}/{self.repo_name}"]
        return []

    def get_repo_string(self) -> str:
        """
        Get repo string in format 'owner/repo'.

        Returns:
            Repository identifier string
        """
        return f"{self.repo_owner}/{self.repo_name}"
