"""Unit tests for ReleaseService."""

from titan_plugin_github.clients.services import ReleaseService
from titan_cli.core.result import ClientSuccess, ClientError
from titan_plugin_github.exceptions import GitHubAPIError


def release_service(mock_gh_network):
    """Create a ReleaseService instance."""
    return ReleaseService(mock_gh_network)


class TestReleaseServiceCreateRelease:
    """Test ReleaseService.create_release()."""

    def test_create_release_with_generated_notes(self, mock_gh_network):
        service = ReleaseService(mock_gh_network)
        mock_gh_network.get_repo_arg.return_value = ["--repo", "masmovil/ragnarok"]
        mock_gh_network.run_command.side_effect = [
            "",
            '{"tagName":"0.4.1","name":"0.4.1","url":"https://github.com/masmovil/ragnarok/releases/tag/0.4.1","isPrerelease":false}',
        ]

        result = service.create_release(
            tag_name="0.4.1",
            title="0.4.1",
            generate_notes=True,
            verify_tag=True,
        )

        assert isinstance(result, ClientSuccess)
        assert result.data.tag_name == "0.4.1"
        assert result.data.title == "0.4.1"
        assert result.data.url == "https://github.com/masmovil/ragnarok/releases/tag/0.4.1"
        assert result.data.is_prerelease is False
        assert mock_gh_network.run_command.call_args_list[0].args[0] == [
            "release", "create", "0.4.1",
            "--title", "0.4.1",
            "--generate-notes",
            "--verify-tag",
            "--repo", "masmovil/ragnarok",
        ]
        assert mock_gh_network.run_command.call_args_list[1].args[0] == [
            "release", "view", "0.4.1",
            "--json", "tagName,name,url,isPrerelease",
            "--repo", "masmovil/ragnarok",
        ]

    def test_create_release_with_custom_notes(self, mock_gh_network):
        service = ReleaseService(mock_gh_network)
        mock_gh_network.get_repo_arg.return_value = []
        mock_gh_network.run_command.side_effect = [
            "",
            '{"tagName":"0.4.1","name":"Release 0.4.1","url":"https://github.com/masmovil/ragnarok/releases/tag/0.4.1","isPrerelease":false}',
        ]

        result = service.create_release(
            tag_name="0.4.1",
            title="Release 0.4.1",
            notes="Custom notes",
            generate_notes=False,
        )

        assert isinstance(result, ClientSuccess)
        assert result.data.title == "Release 0.4.1"
        assert mock_gh_network.run_command.call_args_list[0].args[0] == [
            "release", "create", "0.4.1",
            "--title", "Release 0.4.1",
            "--notes", "Custom notes",
            "--verify-tag",
        ]

    def test_create_release_prerelease(self, mock_gh_network):
        service = ReleaseService(mock_gh_network)
        mock_gh_network.get_repo_arg.return_value = []
        mock_gh_network.run_command.side_effect = [
            "",
            '{"tagName":"0.5.0-beta.1","name":"0.5.0-beta.1","url":"https://github.com/masmovil/ragnarok/releases/tag/0.5.0-beta.1","isPrerelease":true}',
        ]

        result = service.create_release(
            tag_name="0.5.0-beta.1",
            prerelease=True,
            verify_tag=False,
        )

        assert isinstance(result, ClientSuccess)
        assert result.data.is_prerelease is True
        assert mock_gh_network.run_command.call_args_list[0].args[0] == [
            "release", "create", "0.5.0-beta.1",
            "--prerelease",
        ]

    def test_create_release_api_error(self, mock_gh_network):
        service = ReleaseService(mock_gh_network)
        mock_gh_network.get_repo_arg.return_value = []
        mock_gh_network.run_command.side_effect = GitHubAPIError("tag not found")

        result = service.create_release("0.4.1")

        assert isinstance(result, ClientError)
        assert result.error_code == "API_ERROR"
        assert "tag not found" in result.error_message

    def test_create_release_json_parse_error(self, mock_gh_network):
        service = ReleaseService(mock_gh_network)
        mock_gh_network.get_repo_arg.return_value = []
        mock_gh_network.run_command.side_effect = ["", "{not-json"]

        result = service.create_release("0.4.1")

        assert isinstance(result, ClientError)
        assert result.error_code == "JSON_PARSE_ERROR"

    def test_create_release_rejects_notes_and_generate_notes_together(self, mock_gh_network):
        service = ReleaseService(mock_gh_network)

        result = service.create_release(
            tag_name="0.4.1",
            notes="custom",
            generate_notes=True,
        )

        assert isinstance(result, ClientError)
        assert result.error_code == "INVALID_INPUT"
        mock_gh_network.run_command.assert_not_called()


class TestReleaseServiceListReleases:
    """Test ReleaseService.list_releases()."""

    def test_list_releases_returns_ui_releases(self, mock_gh_network):
        service = ReleaseService(mock_gh_network)
        mock_gh_network.get_repo_arg.return_value = ["--repo", "masorange/titan-cli"]
        mock_gh_network.run_command.return_value = (
            '[{"tagName":"0.6.0","name":"0.6.0","url":"https://github.com/masorange/titan-cli/releases/tag/0.6.0",'
            '"isPrerelease":false,"isDraft":false,"publishedAt":"2026-02-01T00:00:00Z"},'
            '{"tagName":"0.5.0","name":"0.5.0","url":"https://github.com/masorange/titan-cli/releases/tag/0.5.0",'
            '"isPrerelease":false,"isDraft":false,"publishedAt":"2026-01-01T00:00:00Z"}]'
        )

        result = service.list_releases(limit=15)

        assert isinstance(result, ClientSuccess)
        assert [release.tag_name for release in result.data] == ["0.6.0", "0.5.0"]
        assert mock_gh_network.run_command.call_args.args[0] == [
            "release", "list",
            "--limit", "15",
            "--json", "tagName,name,publishedAt,isPrerelease,isDraft",
            "--repo", "masorange/titan-cli",
        ]

    def test_list_releases_excludes_drafts_by_default(self, mock_gh_network):
        service = ReleaseService(mock_gh_network)
        mock_gh_network.get_repo_arg.return_value = []
        mock_gh_network.run_command.return_value = (
            '[{"tagName":"0.6.0","name":"0.6.0","url":"","isPrerelease":false,"isDraft":false},'
            '{"tagName":"0.7.0-draft","name":"0.7.0-draft","url":"","isPrerelease":false,"isDraft":true}]'
        )

        result = service.list_releases()

        assert isinstance(result, ClientSuccess)
        assert [release.tag_name for release in result.data] == ["0.6.0"]

    def test_list_releases_api_error(self, mock_gh_network):
        service = ReleaseService(mock_gh_network)
        mock_gh_network.get_repo_arg.return_value = []
        mock_gh_network.run_command.side_effect = GitHubAPIError("not found")

        result = service.list_releases()

        assert isinstance(result, ClientError)
        assert result.error_code == "API_ERROR"


class TestReleaseServiceGetRelease:
    """Test ReleaseService.get_release()."""

    def test_get_release_returns_ui_release_with_body(self, mock_gh_network):
        service = ReleaseService(mock_gh_network)
        mock_gh_network.get_repo_arg.return_value = ["--repo", "masorange/titan-cli"]
        mock_gh_network.run_command.return_value = (
            '{"tagName":"0.6.0","name":"0.6.0",'
            '"url":"https://github.com/masorange/titan-cli/releases/tag/0.6.0",'
            '"isPrerelease":false,"isDraft":false,"publishedAt":"2026-02-01T00:00:00Z",'
            '"body":"- Added Slack plugin\\n- Fixed thread resolution"}'
        )

        result = service.get_release("0.6.0")

        assert isinstance(result, ClientSuccess)
        assert result.data.tag_name == "0.6.0"
        assert result.data.body == "- Added Slack plugin\n- Fixed thread resolution"
        assert mock_gh_network.run_command.call_args.args[0] == [
            "release", "view", "0.6.0",
            "--json", "tagName,name,url,isPrerelease,isDraft,publishedAt,body",
            "--repo", "masorange/titan-cli",
        ]

    def test_get_release_api_error(self, mock_gh_network):
        service = ReleaseService(mock_gh_network)
        mock_gh_network.get_repo_arg.return_value = []
        mock_gh_network.run_command.side_effect = GitHubAPIError("release not found")

        result = service.get_release("0.6.0")

        assert isinstance(result, ClientError)
        assert result.error_code == "API_ERROR"
