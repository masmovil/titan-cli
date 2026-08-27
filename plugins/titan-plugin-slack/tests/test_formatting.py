from titan_plugin_slack.formatting import SlackFormatter


class TestToMrkdwn:
    def test_converts_bold(self) -> None:
        assert SlackFormatter.to_mrkdwn("This is **bold** text") == "This is *bold* text"

    def test_converts_bold_with_underscores(self) -> None:
        assert SlackFormatter.to_mrkdwn("This is __bold__ text") == "This is *bold* text"

    def test_converts_italic(self) -> None:
        assert SlackFormatter.to_mrkdwn("This is *italic* text") == "This is _italic_ text"

    def test_converts_strikethrough(self) -> None:
        assert SlackFormatter.to_mrkdwn("This is ~~gone~~ text") == "This is ~gone~ text"

    def test_converts_header_to_bold_line(self) -> None:
        assert SlackFormatter.to_mrkdwn("## Release 0.6.0") == "*Release 0.6.0*"

    def test_converts_bullet_list(self) -> None:
        markdown = "- First item\n- Second item"
        assert SlackFormatter.to_mrkdwn(markdown) == "• First item\n• Second item"

    def test_converts_link(self) -> None:
        markdown = "See [the docs](https://example.com/docs) for details"
        assert (
            SlackFormatter.to_mrkdwn(markdown)
            == "See <https://example.com/docs|the docs> for details"
        )

    def test_drops_horizontal_rule(self) -> None:
        markdown = "Before\n\n---\n\nAfter"
        assert SlackFormatter.to_mrkdwn(markdown) == "Before\n\n\n\nAfter"

    def test_leaves_fenced_code_blocks_untouched(self) -> None:
        markdown = "Before\n```python\n**not bold**\n```\nAfter"
        result = SlackFormatter.to_mrkdwn(markdown)
        assert "```python\n**not bold**\n```" in result

    def test_bold_and_italic_do_not_interfere(self) -> None:
        markdown = "A **bold** word and an *italic* word"
        assert SlackFormatter.to_mrkdwn(markdown) == "A *bold* word and an _italic_ word"

    def test_converts_inline_table(self) -> None:
        markdown = "| Name | Version |\n| --- | --- |\n| titan-cli | 0.6.0 |"
        result = SlackFormatter.to_mrkdwn(markdown)
        assert result.startswith("```\n")
        assert result.endswith("\n```")
        assert "Name" in result and "Version" in result
        assert "titan-cli" in result and "0.6.0" in result

    def test_converts_inline_table_with_multiple_rows_aligned(self) -> None:
        markdown = (
            "| Plugin | Version |\n"
            "| --- | --- |\n"
            "| titan-cli | 0.6.0 |\n"
            "| ragnarok | 0.9.3 |"
        )
        result = SlackFormatter.to_mrkdwn(markdown)
        lines = result.strip("`\n").split("\n")
        assert lines[0].startswith("Plugin")
        assert "titan-cli" in lines[2]
        assert "ragnarok" in lines[3]

    def test_converts_inline_table_with_missing_cells(self) -> None:
        markdown = "| Col1 | Col2 |\n| --- | --- |\n| only-one |"
        result = SlackFormatter.to_mrkdwn(markdown)
        assert "only-one" in result
