"""Helpers for community plugin source resolution and update checks."""

import os
import sys
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen, Request

import tomli
from titan_cli.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Raw pyproject.toml URL templates per host (use .format(path=..., version=...))
_RAW_URL_GITHUB    = "https://raw.githubusercontent.com/{path}/{version}/pyproject.toml"
_RAW_URL_GITLAB    = "https://gitlab.com/{path}/-/raw/{version}/pyproject.toml"
_RAW_URL_BITBUCKET = "https://bitbucket.org/{path}/raw/{version}/pyproject.toml"

# Base URL prefixes used to strip host when building the path fragment
_BASE_GITHUB    = "https://github.com/"
_BASE_GITLAB    = "https://gitlab.com/"
_BASE_BITBUCKET = "https://bitbucket.org/"

# HTTP fetch timeout (seconds)
_FETCH_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PluginHost(StrEnum):
    """Supported git hosting providers for community plugin preview."""
    GITHUB    = "github"
    GITLAB    = "gitlab"
    BITBUCKET = "bitbucket"
    UNKNOWN   = "unknown"


class PluginChannel(StrEnum):
    """Installation channel for a community plugin."""
    STABLE    = "stable"
    DEV_LOCAL = "dev_local"


_SUPPORTED_HOSTS = {
    "github.com": PluginHost.GITHUB,
    "gitlab.com": PluginHost.GITLAB,
    "bitbucket.org": PluginHost.BITBUCKET,
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CommunityPluginRecord:
    """Record of an installed community plugin."""

    repo_url: str                        # Base URL without @version (empty for dev_local)
    package_name: str                    # Python package name from pyproject.toml
    titan_plugin_name: str               # Key registered under titan.plugins entry point
    installed_at: str                    # ISO 8601 datetime
    channel: str                         # "stable" | "dev_local"
    dev_local_path: Optional[str]        # Absolute path if channel == dev_local, else None
    requested_ref: Optional[str]         # Tag/SHA the user asked for (stable only), else None
    resolved_commit: Optional[str]       # Actual commit SHA installed (stable only), else None


# ---------------------------------------------------------------------------
# URL parsing and validation
# ---------------------------------------------------------------------------

def _normalise_repo_url(base_url: str) -> tuple[PluginHost, str]:
    """Validate and normalize a repository base URL."""
    parsed = urlsplit(base_url.strip())

    if parsed.scheme != "https":
        raise ValueError("Repository URL must start with https://")
    if parsed.username or parsed.password:
        raise ValueError("Repository URL must not include embedded credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError("Repository URL must not include query parameters or fragments.")
    if parsed.port is not None:
        raise ValueError("Repository URL must not include an explicit port.")

    hostname = (parsed.hostname or "").lower()
    host = _SUPPORTED_HOSTS.get(hostname)
    if not host:
        raise ValueError("Only GitHub, GitLab, and Bitbucket HTTPS repository URLs are supported.")

    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    path_parts = [part for part in path.split("/") if part]
    if len(path_parts) < 2:
        raise ValueError("Repository URL must include both owner/group and repository name.")

    return host, f"https://{hostname}/{'/'.join(path_parts)}"

def parse_repo_url(raw_url: str) -> tuple[str, str]:
    """
    Split a URL+version string into (base_url, version).

    Args:
        raw_url: e.g. "https://github.com/user/plugin@v1.2.0"

    Returns:
        Tuple of (base_url, version)

    Raises:
        ValueError: if no @version suffix is present
    """
    raw_url = raw_url.strip()
    if "@" not in raw_url:
        raise ValueError(
            "No version specified. Include a version tag or commit SHA, "
            "e.g. https://github.com/user/plugin@v1.0.0"
        )
    idx = raw_url.rfind("@")
    base_url = raw_url[:idx]
    version = raw_url[idx + 1:]
    if not version:
        raise ValueError(
            "Version is empty. Include a version tag or commit SHA, "
            "e.g. https://github.com/user/plugin@v1.0.0"
        )
    return base_url, version


def validate_url(raw_url: str) -> None:
    """
    Validate that raw_url is well-formed and includes a version.

    Raises:
        ValueError: with a user-friendly message describing the problem
    """
    raw_url = raw_url.strip()
    if not raw_url:
        raise ValueError("URL cannot be empty.")
    base_url, _ = parse_repo_url(raw_url)
    _normalise_repo_url(base_url)


# ---------------------------------------------------------------------------
# Stable ref → commit SHA resolution
# ---------------------------------------------------------------------------

_FULL_SHA_LEN = 40


def _is_hex(s: str) -> bool:
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def resolve_ref_to_commit_sha(
    base_url: str, ref: str, host: PluginHost, token: Optional[str] = None
) -> tuple[Optional[str], Optional[str]]:
    """
    Resolve a tag, short SHA, or full SHA to an exact 40-char commit SHA.

    This is the security anchor for stable installs: pipx always installs from
    the resolved SHA, so a force-pushed tag cannot inject new code without the
    user explicitly running an update.

    Only full resolution (tag → commit) is supported for GitHub. For other
    hosts, a full 40-char hex SHA is required — partial refs are rejected.

    Returns:
        (sha, None)    on success
        (None, error)  on failure
    """
    # Already a full 40-char hex SHA — accept as-is for all hosts
    if len(ref) == _FULL_SHA_LEN and _is_hex(ref):
        return ref, None

    if host != PluginHost.GITHUB:
        return None, (
            f"Tag resolution is only supported for GitHub. "
            f"For {host} repositories, provide a full commit SHA (40 hex characters)."
        )

    clean = base_url.rstrip("/").removesuffix(".git").removeprefix(_BASE_GITHUB)

    def _api_get(url: str) -> tuple[Optional[dict], Optional[str]]:
        try:
            req = Request(url)
            req.add_header("Accept", "application/vnd.github+json")
            if token:
                req.add_header("Authorization", f"Bearer {token}")
            with urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
                import json
                return json.loads(resp.read().decode("utf-8")), None
        except HTTPError as e:
            if e.code == 404:
                return None, "not_found"
            return None, f"http_{e.code}"
        except (URLError, OSError) as e:
            return None, f"network_error: {e}"

    # Resolve as a tag
    tag_data, _ = _api_get(f"https://api.github.com/repos/{clean}/git/ref/tags/{ref}")
    if tag_data:
        obj = tag_data.get("object", {})
        sha = obj.get("sha", "")
        # Annotated tag: sha points to the tag object, not the commit — follow it
        if obj.get("type") == "tag":
            tag_obj, _ = _api_get(f"https://api.github.com/repos/{clean}/git/tags/{sha}")
            if tag_obj:
                sha = tag_obj.get("object", {}).get("sha", sha)
        if sha:
            return sha, None

    # Resolve as a short SHA
    commit_data, _ = _api_get(f"https://api.github.com/repos/{clean}/commits/{ref}")
    if commit_data:
        sha = commit_data.get("sha", "")
        if sha:
            return sha, None

    return None, (
        f"Could not resolve '{ref}' to a commit SHA. "
        "Provide a version tag (e.g. v1.0.0) or a full commit SHA."
    )


# ---------------------------------------------------------------------------
# Host detection and raw URL building
# ---------------------------------------------------------------------------

def detect_host(base_url: str) -> PluginHost:
    """Detect the git hosting provider from the base URL."""
    try:
        host, _ = _normalise_repo_url(base_url)
        return host
    except ValueError:
        return PluginHost.UNKNOWN


def build_raw_pyproject_url(base_url: str, version: str, host: PluginHost) -> Optional[str]:
    """
    Build the raw URL to fetch pyproject.toml from a known hosting provider.

    Returns None for unknown hosts.
    """
    try:
        _, clean = _normalise_repo_url(base_url)
    except ValueError:
        return None

    match host:
        case PluginHost.GITHUB:
            path = clean.removeprefix(_BASE_GITHUB)
            return _RAW_URL_GITHUB.format(path=path, version=version)
        case PluginHost.GITLAB:
            path = clean.removeprefix(_BASE_GITLAB)
            return _RAW_URL_GITLAB.format(path=path, version=version)
        case PluginHost.BITBUCKET:
            path = clean.removeprefix(_BASE_BITBUCKET)
            return _RAW_URL_BITBUCKET.format(path=path, version=version)
        case PluginHost.UNKNOWN:
            return None


# ---------------------------------------------------------------------------
# pyproject.toml fetching and parsing
# ---------------------------------------------------------------------------

def get_github_token() -> Optional[str]:
    """
    Try to get a GitHub token from the gh CLI.

    Returns the token string, or None if gh is not installed or not authenticated.
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            token = result.stdout.strip()
            return token if token else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def fetch_pyproject_toml(raw_url: str, token: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """
    Fetch the pyproject.toml content from a raw URL.

    Args:
        raw_url: Direct URL to the raw pyproject.toml file.
        token: Optional bearer token for private repositories.

    Returns:
        (content, error) — one of them will be None.
        On success:      (content_str, None)
        On 404:          (None, "not_found")
        On network error:(None, "network_error")
    """
    try:
        req = Request(raw_url)
        if token:
            req.add_header("Authorization", f"token {token}")
        with urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            return resp.read().decode("utf-8"), None
    except HTTPError as e:
        if e.code == 404:
            logger.warning("community_plugin_preview_not_found", url=raw_url, status=e.code)
            return None, "not_found"
        logger.warning("community_plugin_preview_http_error", url=raw_url, status=e.code)
        return None, "network_error"
    except (URLError, OSError) as e:
        logger.warning("community_plugin_preview_network_error", url=raw_url, error=str(e))
        return None, "network_error"


def parse_plugin_metadata(toml_content: str) -> dict:
    """
    Parse pyproject.toml content and extract plugin-relevant metadata.

    Returns a dict with keys:
        name, version, description, authors,
        titan_entry_points (dict), python_deps (list),
        titan_requirement (str | None), parse_error (bool)
    """
    try:
        data = tomli.loads(toml_content)
    except Exception:
        return {
            "name": None, "version": None, "description": None,
            "authors": [], "titan_entry_points": {}, "python_deps": [],
            "titan_requirement": None, "parse_error": True,
        }

    # Support both [project] (PEP 621) and [tool.poetry] layouts
    project = data.get("project", {})
    poetry  = data.get("tool", {}).get("poetry", {})

    name        = project.get("name")        or poetry.get("name")
    version     = project.get("version")     or poetry.get("version")
    description = project.get("description") or poetry.get("description")

    # Authors: PEP 621 → list of dicts; Poetry → list of strings
    pep_authors = project.get("authors", [])
    if pep_authors and isinstance(pep_authors[0], dict):
        authors = [a.get("name", "") for a in pep_authors]
    else:
        authors = pep_authors or poetry.get("authors", [])

    # Titan entry points
    pep_eps    = project.get("entry-points", {}).get("titan.plugins", {})
    poetry_eps = poetry.get("plugins", {}).get("titan.plugins", {})
    titan_entry_points = pep_eps or poetry_eps

    # Dependency names (strip version specifiers)
    pep_deps    = project.get("dependencies", [])
    poetry_deps = list(poetry.get("dependencies", {}).keys())
    if pep_deps:
        dep_names = []
        for dep in pep_deps:
            for sep in [">=", "<=", "!=", "~=", "==", ">"]:
                dep = dep.split(sep)[0]
            dep_names.append(dep.strip())
        python_deps = dep_names
    else:
        python_deps = [d for d in poetry_deps if d.lower() != "python"]

    return {
        "name": name, "version": version, "description": description,
        "authors": authors, "titan_entry_points": titan_entry_points,
        "python_deps": python_deps,
        "titan_requirement": _extract_titan_requirement(pep_deps, poetry.get("dependencies", {})),
        "parse_error": False,
    }


_TITAN_DIST_NAMES = ("titan-cli", "titan_cli")


def _extract_titan_requirement(pep_deps: list, poetry_deps: dict) -> Optional[str]:
    """Extract the version specifier a plugin declares on titan-cli, if any."""
    for dep in pep_deps:
        try:
            from packaging.requirements import Requirement
            req = Requirement(dep)
        except Exception:
            continue
        if req.name.lower().replace("_", "-") == "titan-cli":
            return str(req.specifier) or None

    for dist_name in _TITAN_DIST_NAMES:
        constraint = poetry_deps.get(dist_name)
        if constraint is None:
            continue
        if isinstance(constraint, dict):
            constraint = constraint.get("version")
        if isinstance(constraint, str) and constraint.strip():
            return _poetry_constraint_to_specifier(constraint.strip())
    return None


def _poetry_constraint_to_specifier(constraint: str) -> Optional[str]:
    """Translate a Poetry constraint (^x.y, ~x.y, plain specifiers) to PEP 440."""
    if constraint == "*":
        return None
    if constraint[0] in ("^", "~"):
        base = constraint[1:].strip()
        parts = base.split(".")
        try:
            numbers = [int(p) for p in parts]
        except ValueError:
            return None
        if constraint[0] == "^":
            # ^ bumps the leftmost non-zero component
            upper = numbers.copy()
            for i, n in enumerate(upper):
                if n != 0 or i == len(upper) - 1:
                    upper = upper[: i + 1]
                    upper[i] += 1
                    break
        else:
            # ~ allows patch-level changes when minor is given, minor-level otherwise
            upper = numbers[:2] if len(numbers) >= 2 else numbers[:1]
            upper[-1] += 1
        return f">={base},<{'.'.join(str(n) for n in upper)}"
    return constraint


def get_titan_incompatibility(metadata: dict, current_version: str) -> Optional[str]:
    """
    Return a human-readable message when the plugin's declared titan-cli
    requirement excludes the running version, or None when compatible.

    Absent or unparseable requirements never block: plugins are not required
    to declare bounds, and a broken specifier should not brick loading.
    """
    requirement = metadata.get("titan_requirement")
    if not requirement:
        return None
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
        specifier = SpecifierSet(requirement)
        version = Version(current_version)
    except Exception:
        return None
    if version in specifier:
        return None
    return (
        f"requires titan-cli {requirement}, but titan-cli {current_version} is running. "
        "Update the plugin or Titan so the versions match."
    )


def is_running_in_pipx() -> bool:
    """Detect whether Titan is currently running inside a pipx-managed venv."""
    executable = sys.executable
    if "pipx" in executable:
        return True
    return False


def is_running_in_poetry() -> bool:
    """Detect whether Titan is currently running inside a Poetry-managed venv."""
    if os.environ.get("POETRY_ACTIVE"):
        return True
    executable = sys.executable
    if ".venv" in executable:
        return True
    return False


def check_for_update(record: CommunityPluginRecord, token: Optional[str] = None) -> Optional[str]:
    """
    Check if a newer version is available for a community plugin.

    Queries the hosting provider's API for the latest release tag and compares
    it with the installed version. Only works for GitHub, GitLab, Bitbucket with
    tagged releases. Returns None if already up to date, unreachable, or using
    a commit SHA as version. Always returns None for dev_local records.

    Args:
        record: The installed community plugin record.
        token: Optional bearer token for private repositories.

    Returns:
        The latest version string if an update is available, None otherwise.
    """
    if record.channel == PluginChannel.DEV_LOCAL:
        return None

    host = detect_host(record.repo_url)
    clean = record.repo_url.rstrip("/").removesuffix(".git")

    try:
        if host == PluginHost.GITHUB:
            path = clean.removeprefix(_BASE_GITHUB)
            api_url = f"https://api.github.com/repos/{path}/releases/latest"
            req = Request(api_url)
            req.add_header("Accept", "application/vnd.github+json")
            if token:
                req.add_header("Authorization", f"Bearer {token}")
            with urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
                import json
                data = json.loads(resp.read().decode("utf-8"))
            latest = data.get("tag_name")

        elif host == PluginHost.GITLAB:
            path = clean.removeprefix(_BASE_GITLAB)
            encoded = path.replace("/", "%2F")
            api_url = f"https://gitlab.com/api/v4/projects/{encoded}/releases"
            req = Request(api_url)
            if token:
                req.add_header("PRIVATE-TOKEN", token)
            with urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
                import json
                releases = json.loads(resp.read().decode("utf-8"))
            latest = releases[0].get("tag_name") if releases else None

        else:
            return None

        if not latest:
            return None

        # Only suggest update if latest is strictly newer than the recorded version
        current = record.requested_ref or ""
        try:
            from packaging.version import Version
            if Version(latest.lstrip("v")) <= Version(current.lstrip("v")):
                return None
        except Exception:
            # If version parsing fails, fall back to string equality check
            if latest == current:
                return None

        return latest

    except Exception:
        return None


def check_for_updates(
    records: list[CommunityPluginRecord],
    token: Optional[str] = None,
) -> list[tuple[CommunityPluginRecord, str]]:
    """
    Check for updates for a list of community plugin records.

    Args:
        records: Installed community plugin records to check.
        token: Optional bearer token.

    Returns:
        List of (record, latest_version) tuples for plugins with available updates.
    """
    updates = []
    for record in records:
        latest = check_for_update(record, token)
        if latest:
            updates.append((record, latest))
    return updates
