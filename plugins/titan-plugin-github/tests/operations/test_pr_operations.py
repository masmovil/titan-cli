from titan_plugin_github.models.view import UIComment, UICommentThread
from titan_plugin_github.operations.pr_operations import (
    build_quote_reply,
    split_titan_review_body,
)


def _general_thread(body: str, comment_id: int = 555) -> UICommentThread:
    comment = UIComment(
        id=comment_id,
        body=body,
        author_login="reviewer",
        author_name="Reviewer",
        formatted_date="31/07/2026 06:11:38",
    )
    return UICommentThread(
        thread_id=f"general_{comment_id}",
        main_comment=comment,
        replies=[],
        is_resolved=False,
        is_outdated=False,
    )


TITAN_BODY = (
    "**src/foo.py** (line 866):\n"
    "The marker points at the wrong line.\n\n"
    "Second paragraph of the same finding.\n\n"
    "---\n\n"
    "**src/bar.py** (line 265):\n"
    "This gate checks the wrong field.\n\n"
    "---\n\n"
    "General:\n"
    "A finding without a path."
)


class TestSplitTitanReviewBody:
    def test_titan_body_splits_into_one_thread_per_finding(self):
        parts = split_titan_review_body(_general_thread(TITAN_BODY))

        assert len(parts) == 3
        assert parts[0].main_comment.path == "src/foo.py"
        assert parts[0].main_comment.line == 866
        assert parts[0].main_comment.body.startswith("The marker points")
        # multi-paragraph finding bodies stay whole
        assert "Second paragraph" in parts[0].main_comment.body
        assert parts[1].main_comment.path == "src/bar.py"
        assert parts[1].main_comment.line == 265
        assert parts[2].main_comment.path is None
        assert parts[2].main_comment.line is None

    def test_split_parts_are_general_comments_with_unique_ids(self):
        parts = split_titan_review_body(_general_thread(TITAN_BODY))

        assert all(p.is_general_comment for p in parts)
        ids = [p.main_comment.id for p in parts]
        assert len(set(ids)) == 3
        # Synthetic ids are negative so they can never collide with real
        # (positive) GitHub comment ids in the reply/commit maps.
        assert all(i < 0 for i in ids)

    def test_split_parts_keep_author_and_date(self):
        parts = split_titan_review_body(_general_thread(TITAN_BODY))

        assert parts[0].main_comment.author_login == "reviewer"
        assert parts[0].main_comment.formatted_date == "31/07/2026 06:11:38"

    def test_human_general_comment_is_returned_unchanged(self):
        thread = _general_thread("Nice PR! Just one question about the approach.")

        assert split_titan_review_body(thread) == [thread]

    def test_body_with_separator_but_non_titan_sections_is_not_split(self):
        thread = _general_thread("Intro text\n\n---\n\nSome unrelated footer")

        assert split_titan_review_body(thread) == [thread]

    def test_mixed_body_with_one_non_matching_section_is_not_split(self):
        body = TITAN_BODY + "\n\n---\n\nTrailing human note"
        thread = _general_thread(body)

        assert split_titan_review_body(thread) == [thread]

    def test_inline_thread_is_never_split(self):
        comment = UIComment(
            id=1,
            body=TITAN_BODY,
            author_login="reviewer",
            author_name="Reviewer",
            formatted_date="",
        )
        thread = UICommentThread(
            thread_id="RT_abc123",
            main_comment=comment,
            replies=[],
            is_resolved=False,
            is_outdated=False,
        )

        assert split_titan_review_body(thread) == [thread]

    def test_single_section_titan_body_splits(self):
        thread = _general_thread("**src/foo.py** (line 12):\nOne single finding.")

        parts = split_titan_review_body(thread)

        assert len(parts) == 1
        assert parts[0].main_comment.path == "src/foo.py"
        assert parts[0].main_comment.line == 12
        assert parts[0].main_comment.body == "One single finding."


class TestBuildQuoteReply:
    def test_quotes_original_before_reply(self):
        result = build_quote_reply("Original comment", "My answer")

        assert result == "> Original comment\n\nMy answer"

    def test_quotes_every_line_of_a_short_original(self):
        result = build_quote_reply("line one\nline two", "ok")

        assert result == "> line one\n> line two\n\nok"

    def test_long_original_is_truncated_with_ellipsis(self):
        original = "\n".join(f"line {i}" for i in range(1, 11))

        result = build_quote_reply(original, "ok", max_quote_lines=3)

        assert result.startswith("> line 1\n> line 2\n> line 3\n> […]\n\nok")
        assert "> line 4" not in result
