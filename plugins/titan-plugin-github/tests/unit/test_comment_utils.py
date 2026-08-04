"""Tests for comment body parsing/rendering helpers.

Focus: HTML bot bodies. Textual's Markdown widget has no `html_block`/`html_inline`
handling, so an HTML-only body (how linter/CI bots format their findings) used to
render as an EMPTY comment — the thread was visible but its message was not.
"""

from titan_plugin_github.widgets.comment_utils import (
    CodeBlockElement,
    TextElement,
    html_body_to_text,
    parse_comment_body,
)

# Real body from masmovil/ragnarok-android PR #3601 (github-actions lint thread).
BOT_TABLE_BODY = """<table data-meta="generated_by_guuk">
  <tbody>
    <tr>
      <td>:warning:</td>
      <td width="100%" data-sticky="false"><span data-href="https://github.com/masmovil/ragnarok-android/blob/49cdfb9/app/src/main/kotlin/com/ragnarok/apps/ui/components/webcontent/WebContent.kt#L280"></span><code>onTouch</code> lambda should call <code>View#performClick</code> when a click is detected</td>
    </tr>
  </tbody>
</table>"""


def test_bot_table_body_renders_readable_text():
    elements = parse_comment_body(body=BOT_TABLE_BODY)

    assert len(elements) == 1
    assert isinstance(elements[0], TextElement)
    # The severity marker joins the message it qualifies, code spans become backticks,
    # and no HTML survives.
    assert elements[0].content == (
        "⚠️ `onTouch` lambda should call `View#performClick` when a click is detected"
    )
    assert "<" not in elements[0].content


def test_html_comment_wrapper_is_stripped_but_content_kept():
    """Danger-style bodies start with an HTML comment holding a summary, then HTML."""
    body = (
        "<!--\n  3 Errors: Unit tests failed\n-->\n"
        "<table><tr><td>:no_entry_sign:</td><td>Unit tests failed for flavor Guuk</td></tr></table>"
    )

    text = html_body_to_text(body)

    assert "🚫 Unit tests failed for flavor Guuk" in text
    assert "<!--" not in text
    assert "3 Errors" not in text  # the hidden summary stays hidden


def test_html_entities_and_line_breaks():
    body = "<div>a &amp; b<br>second line &lt;tag&gt;</div>"

    text = html_body_to_text(body)

    assert text == "a & b\nsecond line <tag>"


def test_plain_markdown_body_is_untouched():
    body = "This is **bold** and `code`.\n\n```kotlin\nval x = 1\n```"

    elements = parse_comment_body(body=body)

    assert isinstance(elements[0], TextElement)
    assert elements[0].content == "This is **bold** and `code`."
    assert isinstance(elements[1], CodeBlockElement)
    assert elements[1].code.strip() == "val x = 1"


def test_inline_html_in_otherwise_markdown_body_keeps_the_prose():
    """A human comment with a stray <img>/<br> must not lose its text."""
    body = "Please fix this.<br>See <a href='http://x'>the docs</a>."

    elements = parse_comment_body(body=body)

    assert elements[0].content == "Please fix this.\nSee the docs."


def test_html_only_decoration_yields_no_elements():
    """A body with nothing but markup (e.g. a bare image badge) renders nothing
    instead of raw tags."""
    assert parse_comment_body(body='<img src="badge.svg">') == []


# ============================================================================
# Regressions caught by Titan's own review of the 014 fix (2026-08-04)
# ============================================================================


def test_prose_comparisons_are_not_mistaken_for_html():
    """`< a` / `y >` in a human comment used to trigger the HTML path, and the
    tag-stripping regex then deleted everything between them — silent content loss in
    an ordinary review comment."""
    body = "Check that `x < a` and `y > b` before calling this."

    elements = parse_comment_body(body=body)

    assert len(elements) == 1
    assert elements[0].content == body


def test_fenced_code_blocks_keep_generics_verbatim():
    """Flattening used to run on the WHOLE body before fenced blocks were split, so
    `List<String>` inside a code block lost its type argument."""
    body = "Use this instead:\n\n```kotlin\nval names: List<String> = emptyList()\nif (a < p) return\n```"

    elements = parse_comment_body(body=body)

    assert isinstance(elements[1], CodeBlockElement)
    assert elements[1].code == "val names: List<String> = emptyList()\nif (a < p) return"


def test_suggestion_block_is_never_flattened():
    """A mangled ```suggestion is worse than a blank one: it gets applied to the code."""
    body = "Fix:\n\n```suggestion\nval x: Map<String, Int> = mapOf()\n```"

    elements = parse_comment_body(body=body)

    suggestion = elements[1]
    assert suggestion.code == "val x: Map<String, Int> = mapOf()"


def test_prose_mixed_with_real_html_still_flattens_the_html():
    body = "See the table:<br><table><tr><td>:warning:</td><td>be careful</td></tr></table>"

    elements = parse_comment_body(body=body)

    assert elements[0].content == "See the table:\n⚠️ be careful"
