# plugins/titan-plugin-github/titan_plugin_github/clients/services/contents_service.py
"""
Contents Service

Business logic for navigating a GitHub repository's contents (Contents API).
Uses gh CLI through the network layer.
"""

import json
from typing import List, Optional
from urllib.parse import quote, urlencode

from titan_cli.core.result import ClientResult, ClientSuccess, ClientError
from titan_cli.core.logging import log_client_operation

from ..network import GHNetwork
from ...exceptions import GitHubAPIError


class ContentsService:
    """
    Service for GitHub repository contents operations.

    Lets callers navigate a repository's tree (list a directory, check whether
    a path exists) without cloning it locally.
    """

    def __init__(self, gh_network: GHNetwork):
        """
        Initialize contents service.

        Args:
            gh_network: GHNetwork instance for REST/CLI operations
        """
        self.gh = gh_network

    def _contents_endpoint(
        self,
        path: str,
        ref: Optional[str],
        repo_owner: Optional[str],
        repo_name: Optional[str],
    ) -> List[str]:
        owner = repo_owner or self.gh.repo_owner
        name = repo_name or self.gh.repo_name
        clean_path = "/".join(quote(segment) for segment in path.strip("/").split("/") if segment)

        endpoint = f"repos/{owner}/{name}/contents"
        if clean_path:
            endpoint = f"{endpoint}/{clean_path}"
        if ref:
            endpoint = f"{endpoint}?{urlencode({'ref': ref})}"

        return ["api", endpoint]

    @staticmethod
    def _is_not_found(error: GitHubAPIError) -> bool:
        return "404" in (error.stderr or "")

    @log_client_operation()
    def list_directory(
        self,
        path: str,
        ref: Optional[str] = None,
        *,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
    ) -> ClientResult[List[dict]]:
        """
        List the entries of a directory in a repository.

        Args:
            path: Directory path relative to the repo root ("" for repo root)
            ref: Optional branch/tag/commit SHA to read from (defaults to the repo's default branch)
            repo_owner: Optional owner override (defaults to the client's configured repo)
            repo_name: Optional repo name override (defaults to the client's configured repo)

        Returns:
            ClientResult[List[dict]] with entries shaped like
            {"name": str, "path": str, "type": "dir" | "file"}
        """
        try:
            args = self._contents_endpoint(path, ref, repo_owner, repo_name)
            output = self.gh.run_command(args)
            data = json.loads(output)

            if isinstance(data, dict):
                return ClientError(
                    error_message=f"'{path}' is a file, not a directory",
                    error_code="NOT_A_DIRECTORY",
                )

            entries = [
                {"name": item["name"], "path": item["path"], "type": item["type"]}
                for item in data
            ]

            return ClientSuccess(
                data=entries,
                message=f"Retrieved {len(entries)} entries from '{path or '/'}'"
            )

        except json.JSONDecodeError as e:
            return ClientError(
                error_message=f"Failed to parse contents data: {e}",
                error_code="JSON_PARSE_ERROR",
            )
        except GitHubAPIError as e:
            if self._is_not_found(e):
                return ClientError(
                    error_message=f"Path '{path}' not found",
                    error_code="NOT_FOUND",
                )
            return ClientError(error_message=str(e), error_code="API_ERROR")

    @log_client_operation()
    def path_exists(
        self,
        path: str,
        ref: Optional[str] = None,
        *,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
    ) -> ClientResult[bool]:
        """
        Check whether a path exists in a repository.

        Args:
            path: Path relative to the repo root
            ref: Optional branch/tag/commit SHA to check against (defaults to the repo's default branch)
            repo_owner: Optional owner override (defaults to the client's configured repo)
            repo_name: Optional repo name override (defaults to the client's configured repo)

        Returns:
            ClientResult[bool]
        """
        try:
            args = self._contents_endpoint(path, ref, repo_owner, repo_name)
            self.gh.run_command(args)
            return ClientSuccess(data=True, message=f"'{path}' exists")
        except GitHubAPIError as e:
            if self._is_not_found(e):
                return ClientSuccess(data=False, message=f"'{path}' does not exist")
            return ClientError(error_message=str(e), error_code="API_ERROR")
