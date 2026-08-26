import pytest

from titan_cli.core.plugins.community_sources import (
    CommunityPluginRecord,
    PluginChannel,
    PluginHost,
    build_raw_pyproject_url,
    check_for_update,
    detect_host,
    resolve_ref_to_commit_sha,
    validate_url,
)


def test_resolve_ref_to_commit_sha_accepts_full_sha_for_any_host():
    sha = "a" * 40

    resolved, error = resolve_ref_to_commit_sha(
        "https://gitlab.com/example/plugin",
        sha,
        PluginHost.GITLAB,
    )

    assert resolved == sha
    assert error is None


def test_validate_url_accepts_supported_https_repo():
    validate_url("https://github.com/example/plugin@v1.0.0")


def test_validate_url_rejects_embedded_credentials():
    with pytest.raises(ValueError, match="embedded credentials"):
        validate_url("https://user:pass@github.com/example/plugin@v1.0.0")


def test_validate_url_rejects_query_and_fragment():
    with pytest.raises(ValueError, match="query parameters or fragments"):
        validate_url("https://github.com/example/plugin?foo=bar@v1.0.0")


def test_validate_url_rejects_host_spoofing():
    with pytest.raises(ValueError, match="Only GitHub, GitLab, and Bitbucket"):
        validate_url("https://evil.com/github.com/example/plugin@v1.0.0")


def test_detect_host_requires_exact_supported_hostname():
    assert detect_host("https://github.com/example/plugin") == PluginHost.GITHUB
    assert detect_host("https://gitlab.com/group/subgroup/plugin") == PluginHost.GITLAB
    assert detect_host("https://evil.com/github.com/example/plugin") == PluginHost.UNKNOWN


def test_build_raw_pyproject_url_normalises_git_suffix():
    url = build_raw_pyproject_url(
        "https://github.com/example/plugin.git",
        "abcdef",
        PluginHost.GITHUB,
    )

    assert url == "https://raw.githubusercontent.com/example/plugin/abcdef/pyproject.toml"


def test_resolve_ref_to_commit_sha_rejects_non_github_partial_refs():
    resolved, error = resolve_ref_to_commit_sha(
        "https://gitlab.com/example/plugin",
        "v1.2.3",
        PluginHost.GITLAB,
    )

    assert resolved is None
    assert "full commit SHA" in error


def test_resolve_ref_to_commit_sha_resolves_annotated_github_tag(mocker):
    responses = [
        {"object": {"type": "tag", "sha": "b" * 40}},
        {"object": {"sha": "c" * 40}},
    ]

    class DummyResponse:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            import json

            return json.dumps(self.payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout):
        return DummyResponse(responses.pop(0))

    mocker.patch(
        "titan_cli.core.plugins.community_sources.urlopen",
        side_effect=fake_urlopen,
    )

    resolved, error = resolve_ref_to_commit_sha(
        "https://github.com/example/plugin",
        "v1.2.3",
        PluginHost.GITHUB,
    )

    assert resolved == "c" * 40
    assert error is None


def test_check_for_update_returns_none_for_dev_local():
    record = CommunityPluginRecord(
        repo_url="",
        package_name="example-plugin",
        titan_plugin_name="example",
        installed_at="2026-04-07T00:00:00+00:00",
        channel=PluginChannel.DEV_LOCAL,
        dev_local_path="/tmp/example-plugin",
        requested_ref=None,
        resolved_commit=None,
    )

    assert check_for_update(record) is None


def test_check_for_update_compares_against_requested_ref(mocker):
    record = CommunityPluginRecord(
        repo_url="https://github.com/example/plugin",
        package_name="example-plugin",
        titan_plugin_name="example",
        installed_at="2026-04-07T00:00:00+00:00",
        channel=PluginChannel.STABLE,
        dev_local_path=None,
        requested_ref="v1.0.0",
        resolved_commit="a" * 40,
    )

    class DummyResponse:
        def read(self):
            import json

            return json.dumps({"tag_name": "v1.1.0"}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    mocker.patch(
        "titan_cli.core.plugins.community_sources.urlopen",
        return_value=DummyResponse(),
    )

    assert check_for_update(record) == "v1.1.0"


# ---------------------------------------------------------------------------
# titan-cli compatibility contract
# ---------------------------------------------------------------------------

from titan_cli.core.plugins.community_sources import (  # noqa: E402
    get_titan_incompatibility,
    parse_plugin_metadata,
)


def test_parse_plugin_metadata_extracts_titan_requirement_pep621():
    metadata = parse_plugin_metadata(
        """
[project]
name = "example-plugin"
version = "0.1.0"
dependencies = ["requests>=2.0", "titan-cli>=0.8.0,<0.9"]
""".strip()
    )
    assert set(metadata["titan_requirement"].split(",")) == {">=0.8.0", "<0.9"}


def test_parse_plugin_metadata_extracts_titan_requirement_poetry_string():
    metadata = parse_plugin_metadata(
        """
[tool.poetry]
name = "example-plugin"
version = "0.1.0"

[tool.poetry.dependencies]
python = ">=3.10,<4.0"
titan-cli = ">=0.6.0"
""".strip()
    )
    assert metadata["titan_requirement"] == ">=0.6.0"


def test_parse_plugin_metadata_translates_poetry_caret_and_dict():
    caret = parse_plugin_metadata(
        """
[tool.poetry]
name = "example-plugin"

[tool.poetry.dependencies]
titan-cli = "^0.8.0"
""".strip()
    )
    assert caret["titan_requirement"] == ">=0.8.0,<0.9"

    as_dict = parse_plugin_metadata(
        """
[tool.poetry]
name = "example-plugin"

[tool.poetry.dependencies]
titan-cli = {version = "~1.2", extras = ["extra"]}
""".strip()
    )
    assert as_dict["titan_requirement"] == ">=1.2,<1.3"


def test_parse_plugin_metadata_without_titan_dependency():
    metadata = parse_plugin_metadata(
        """
[project]
name = "example-plugin"
dependencies = ["requests>=2.0"]
""".strip()
    )
    assert metadata["titan_requirement"] is None


def test_get_titan_incompatibility_detects_version_outside_bounds():
    metadata = {"titan_requirement": ">=0.8.0,<0.9"}

    assert get_titan_incompatibility(metadata, "0.8.5") is None
    message = get_titan_incompatibility(metadata, "0.7.2")
    assert message is not None
    assert ">=0.8.0,<0.9" in message
    assert "0.7.2" in message


def test_get_titan_incompatibility_never_blocks_on_missing_or_broken_specifier():
    assert get_titan_incompatibility({"titan_requirement": None}, "0.8.0") is None
    assert get_titan_incompatibility({}, "0.8.0") is None
    assert get_titan_incompatibility({"titan_requirement": "not a specifier"}, "0.8.0") is None
