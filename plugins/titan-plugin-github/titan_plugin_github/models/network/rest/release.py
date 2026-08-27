"""
Network model for GitHub release data returned by gh CLI JSON output.
"""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class NetworkRelease:
    """
    Raw GitHub release model faithful to gh CLI JSON fields.
    """
    tag_name: str
    name: str
    url: str
    is_prerelease: bool
    body: str = ""
    published_at: str = ""
    is_draft: bool = False

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "NetworkRelease":
        """
        Parse raw gh JSON into NetworkRelease.
        """
        return cls(
            tag_name=data.get("tagName", ""),
            name=data.get("name", "") or data.get("tagName", ""),
            url=data.get("url", ""),
            is_prerelease=bool(data.get("isPrerelease", False)),
            body=data.get("body", "") or "",
            published_at=data.get("publishedAt", "") or "",
            is_draft=bool(data.get("isDraft", False)),
        )
