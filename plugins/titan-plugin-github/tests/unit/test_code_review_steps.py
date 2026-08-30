import threading
from unittest.mock import Mock

from titan_cli.core.result import ClientError, ClientSuccess
from titan_cli.engine import WorkflowContext
from titan_cli.engine.interaction.base import ItemReviewResponse
from titan_cli.engine.results import Error, Exit, Skip, Success
from titan_cli.ports.protocol import ItemReviewDecision
from titan_cli.external_cli.adapters import HeadlessResponse
from titan_cli.external_cli.adapters.base import SupportedCLI
from titan_plugin_github.models.review_enums import FileReadMode, FileReviewPriority, FindingSeverity, PRSizeClass, ReviewActionSource, ReviewActionType, ReviewStrategyType
from titan_plugin_github.models.review_models import (
    ChangeManifest,
    FileContextEntry,
    Finding,
    FocusContextBatch,
    PullRequestManifest,
    ReferencedCommitContext,
    ReviewStrategy,
    ReviewActionProposal,
    ScoredReviewCandidate,
    ThreadReviewCandidate,
    ThreadReviewContext,
)
from titan_plugin_github.models.review_enums import FileChangeStatus
from titan_plugin_github.models.review_profile_models import ReviewProfile
from titan_plugin_github.models.view import UIComment, UICommentThread, UIFileChange, UIPullRequest
import titan_plugin_github.steps.code_review_steps as code_review_steps
from titan_plugin_github.steps.code_review_steps import (
    ai_review_findings,
    ai_thread_resolution,
    build_thread_review_candidates,
    build_thread_review_contexts,
    fetch_pr_review_bundle,
    score_review_candidates,
    verify_findings,
)


class _FakeTextual:
    def begin_step(self, _name):
        pass

    def end_step(self, _status):
        pass

    def dim_text(self, _text):
        pass

    def warning_text(self, _text):
        pass

    def error_text(self, _text):
        pass

    def success_text(self, _text):
        pass

    def text(self, _text):
        pass

    def bold_text(self, _text):
        pass

    def show_diff_stat(self, *_args, **_kwargs):
        pass

    class _Loading:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def loading(self, _text):
        return self._Loading()

    def ai_chip(self, _text):
        pass


def _make_pr(
    *, is_cross_repository: bool, author_name: str = "forkuser", head_repository_name: str = "some-repo"
) -> UIPullRequest:
    return UIPullRequest(
        number=223,
        title="Poeditor plugin implementation",
        body="Body",
        status_icon="🟢",
        state="OPEN",
        author_name=author_name,
        head_ref="poeditor-plugin",
        base_ref="master",
        branch_info="poeditor-plugin → master",
        stats="+10 -0",
        files_changed=2,
        is_mergeable=True,
        is_draft=False,
        review_summary="No reviews",
        labels=[],
        formatted_created_at="",
        formatted_updated_at="",
        is_cross_repository=is_cross_repository,
        head_repository_owner="forkuser" if is_cross_repository else "base-org",
        head_repository_name=head_repository_name if is_cross_repository else None,
    )


def _make_file(path: str) -> UIFileChange:
    return UIFileChange(
        path=path,
        additions=10,
        deletions=0,
        status=FileChangeStatus.ADDED,
        status_icon="+",
    )


def _make_context(sample_pr: UIPullRequest) -> WorkflowContext:
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.github = Mock()
    ctx.git = Mock()
    ctx.data["review_pr_number"] = sample_pr.number
    ctx.github.get_pull_request.return_value = ClientSuccess(data=sample_pr, message="ok")
    ctx.github.get_pr_files_with_stats.return_value = ClientSuccess(
        data=[_make_file("plugins/titan-plugin-poeditor/plugin.py")],
        message="ok",
    )
    ctx.github.get_pr_commit_sha.return_value = ClientSuccess(data="abc123", message="ok")
    ctx.github.get_pr_review_threads.return_value = ClientSuccess(data=[], message="ok")
    ctx.github.get_pr_general_comments.return_value = ClientSuccess(data=[], message="ok")
    ctx.github.get_current_user.return_value = ClientSuccess(data="reviewer", message="ok")
    ctx.github.get_pr_template.return_value = None
    return ctx


def test_fetch_pr_review_bundle_uses_github_diff_for_cross_repo_pr():
    pr = _make_pr(is_cross_repository=True)
    ctx = _make_context(pr)
    ctx.github.get_pr_diff.return_value = ClientSuccess(data="diff --git a/foo b/foo", message="ok")

    result = fetch_pr_review_bundle(ctx)

    assert isinstance(result, Success)
    assert result.metadata["review_diff"] == "diff --git a/foo b/foo"
    ctx.github.get_pr_diff.assert_called_once_with(223)
    ctx.git.get_branch_diff.assert_not_called()


def test_fetch_pr_review_bundle_falls_back_to_github_diff_when_git_diff_empty():
    pr = _make_pr(is_cross_repository=False)
    ctx = _make_context(pr)
    ctx.git.fetch.return_value = ClientSuccess(data=None, message="ok")
    ctx.git.get_branch_diff.return_value = ClientSuccess(data="", message="empty")
    ctx.github.get_pr_diff.return_value = ClientSuccess(data="diff --git a/foo b/foo", message="ok")

    result = fetch_pr_review_bundle(ctx)

    assert isinstance(result, Success)
    assert result.metadata["review_diff"] == "diff --git a/foo b/foo"
    ctx.git.get_branch_diff.assert_called_once()
    ctx.github.get_pr_diff.assert_called_once_with(223)


def test_fetch_pr_review_bundle_falls_back_to_github_diff_when_git_diff_fails():
    pr = _make_pr(is_cross_repository=False)
    ctx = _make_context(pr)
    ctx.git.fetch.return_value = ClientSuccess(data=None, message="ok")
    from titan_cli.core.result import ClientError

    ctx.git.get_branch_diff.return_value = ClientError(error_message="unknown revision")
    ctx.github.get_pr_diff.return_value = ClientSuccess(data="diff --git a/foo b/foo", message="ok")

    result = fetch_pr_review_bundle(ctx)

    assert isinstance(result, Success)
    assert result.metadata["review_diff"] == "diff --git a/foo b/foo"
    ctx.github.get_pr_diff.assert_called_once_with(223)


def test_fetch_pr_review_bundle_uses_local_u3_diff_when_github_diff_unavailable():
    """GitHub refuses diffs over 20k lines (406). The publishable-lines source then
    comes from a local 3-context diff instead of degrading to added-lines-only."""
    pr = _make_pr(is_cross_repository=False)
    ctx = _make_context(pr)
    from titan_cli.core.result import ClientError

    u20_diff = "diff --git a/foo b/foo\n--- a/foo\n+++ b/foo\n@@ -1,1 +1,2 @@\n line1\n+added\n"
    u3_diff = "diff --git a/foo b/foo\n--- a/foo\n+++ b/foo\n@@ -1,1 +1,2 @@\n line1\n+added\n"
    ctx.git.fetch.return_value = ClientSuccess(data=None, message="ok")
    ctx.git.get_branch_diff.side_effect = [
        ClientSuccess(data=u20_diff, message="ok"),
        ClientSuccess(data=u3_diff, message="ok"),
    ]
    ctx.github.get_pr_diff.return_value = ClientError(
        error_message="HTTP 406: diff exceeded the maximum number of lines (20000)"
    )

    result = fetch_pr_review_bundle(ctx)

    assert isinstance(result, Success)
    assert result.metadata["review_diff_manager"].has_github_diff is True
    # Second get_branch_diff call is the publish-validation source, at 3 context lines.
    validation_call = ctx.git.get_branch_diff.call_args_list[1]
    assert validation_call.kwargs.get("context_lines") == 3


def test_fetch_pr_review_bundle_exits_when_pr_has_no_files_and_no_diff():
    pr = _make_pr(is_cross_repository=True)
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.github = Mock()
    ctx.git = Mock()
    ctx.data["review_pr_number"] = pr.number
    ctx.github.get_pull_request.return_value = ClientSuccess(data=pr, message="ok")
    ctx.github.get_pr_files_with_stats.return_value = ClientSuccess(data=[], message="ok")
    ctx.github.get_pr_commit_sha.return_value = ClientSuccess(data="abc123", message="ok")
    ctx.github.get_pr_diff.return_value = ClientSuccess(data="", message="empty")

    result = fetch_pr_review_bundle(ctx)

    assert isinstance(result, Exit)
    assert result.message == "Empty PR diff"


def test_fetch_pr_review_bundle_includes_current_github_user():
    pr = _make_pr(is_cross_repository=True)
    ctx = _make_context(pr)
    ctx.github.get_pr_diff.return_value = ClientSuccess(data="diff --git a/foo b/foo", message="ok")

    result = fetch_pr_review_bundle(ctx)

    assert isinstance(result, Success)
    assert result.metadata["review_current_user"] == "reviewer"
    ctx.github.get_current_user.assert_called_once_with()


def test_build_thread_review_candidates_filters_to_current_user_threads():
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_pr"] = _make_pr(is_cross_repository=False, author_name="author")
    ctx.data["review_current_user"] = "reviewer"
    ctx.data["review_threads"] = [
        _make_thread(reply_body="Fixed", path="src/main.py", line=42, body="Please fix this"),
        UICommentThread(
            thread_id="thread_456",
            main_comment=UIComment(
                id=20,
                body="Please fix this too",
                author_login="other-reviewer",
                author_name="Other Reviewer",
                formatted_date="",
                path="src/other.py",
                line=10,
            ),
            replies=[
                UIComment(
                    id=21,
                    body="Done",
                    author_login="gabrielglbh",
                    author_name="gabrielglbh",
                    formatted_date="",
                    path="src/other.py",
                    line=10,
                )
            ],
            is_resolved=False,
            is_outdated=False,
        ),
    ]

    result = build_thread_review_candidates(ctx)

    assert isinstance(result, Success)
    candidates = ctx.data["thread_review_candidates"]
    assert len(candidates) == 1
    assert candidates[0].main_comment_author == "reviewer"


def test_build_thread_review_candidates_errors_without_current_user():
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_pr"] = _make_pr(is_cross_repository=False)
    ctx.data["review_threads"] = []

    result = build_thread_review_candidates(ctx)

    assert isinstance(result, Error)
    assert result.message == "Current GitHub user not available"


def test_score_review_candidates_exits_when_no_reviewable_candidates_remain():
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["change_manifest"] = ChangeManifest(
        pr=PullRequestManifest(
            number=215,
            title="docs-only cleanup",
            base="master",
            head="cleanup",
            author="alex",
            description="Body",
        ),
        files=[
            MockChangedFile(
                path="docs/readme.md",
                status="modified",
                additions=1,
                deletions=0,
                is_docs=True,
            )
        ],
        total_additions=1,
        total_deletions=0,
    )

    result = score_review_candidates(ctx)

    assert isinstance(result, Exit)
    assert result.message == "No reviewable candidates after exclusions"


def MockChangedFile(**kwargs):
    from titan_plugin_github.models.review_models import ChangedFileEntry

    return ChangedFileEntry(**kwargs)


def _make_thread(*, reply_body: str, path: str, line: int, body: str) -> UICommentThread:
    return UICommentThread(
        thread_id="thread_123",
        main_comment=UIComment(
            id=10,
            body=body,
            author_login="reviewer",
            author_name="Reviewer",
            formatted_date="",
            path=path,
            line=line,
            diff_hunk="@@ -541,3 +541,3 @@\n-fun ButtonDialog(dialogState: DialogState = rememberDialogState(false))\n+fun ButtonDialog(dialogState: DialogState)\n",
        ),
        replies=[
            UIComment(
                id=11,
                body=reply_body,
                author_login="author",
                author_name="Author",
                formatted_date="",
                path=path,
                line=line,
            )
        ],
        is_resolved=False,
        is_outdated=False,
    )


def test_build_thread_review_contexts_includes_referenced_commit_contexts():
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.github = Mock()
    ctx.data["thread_review_candidates"] = [
        ThreadReviewCandidate(
            thread_id="thread_123",
            path="freyja-core/src/main/kotlin/es/masorange/freyja/core/components/buttons/Buttons.kt",
            line=543,
            main_comment_body="Please fix the dialog state wiring",
            main_comment_author="reviewer",
            replies_count=1,
            last_reply_author="author",
            last_reply_body="Fixed in 343e2e9d7402d0afccfd35a9ecc8e6ea341031c6",
        )
    ]
    ctx.data["review_threads"] = [
        _make_thread(
            reply_body="Fixed in 343e2e9d7402d0afccfd35a9ecc8e6ea341031c6",
            path="freyja-core/src/main/kotlin/es/masorange/freyja/core/components/buttons/Buttons.kt",
            line=543,
            body="Please fix the dialog state wiring",
        )
    ]
    ctx.data["review_diff"] = (
        "diff --git a/freyja-core/src/main/kotlin/es/masorange/freyja/core/components/buttons/Buttons.kt "
        "b/freyja-core/src/main/kotlin/es/masorange/freyja/core/components/buttons/Buttons.kt\n"
        "@@ -541,3 +541,3 @@\n"
        "-fun ButtonDialog(dialogState: DialogState = rememberDialogState(false))\n"
        "+fun ButtonDialog(dialogState: DialogState)\n"
    )
    ctx.github.get_commit_review_context.return_value = ClientSuccess(
        data=ReferencedCommitContext(
            sha="343e2e9d7402d0afccfd35a9ecc8e6ea341031c6",
            abbreviated_sha="343e2e9",
            message="remove default state value",
            changed_files=["freyja-core/src/main/kotlin/.../BaseDialog.kt"],
            patch_excerpt="diff --git a/freyja-core/src/main/kotlin/.../BaseDialog.kt b/freyja-core/src/main/kotlin/.../BaseDialog.kt",
        ),
        message="ok",
    )

    result = build_thread_review_contexts(ctx)

    assert isinstance(result, Success)
    contexts = ctx.data["thread_review_contexts"]
    assert len(contexts) == 1
    assert contexts[0].referenced_commits[0].abbreviated_sha == "343e2e9"
    ctx.github.get_commit_review_context.assert_called_once_with(
        "343e2e9d7402d0afccfd35a9ecc8e6ea341031c6",
        repo_owner=None,
        repo_name=None,
        max_files=3,
        max_patch_chars=4000,
    )


def test_build_thread_review_contexts_resolves_referenced_commits_against_fork_head_repo():
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.github = Mock()
    ctx.data["review_pr"] = _make_pr(is_cross_repository=True, author_name="author", head_repository_name="fork-repo")
    ctx.data["thread_review_candidates"] = [
        ThreadReviewCandidate(
            thread_id="thread_123",
            path="freyja-core/src/main/kotlin/es/masorange/freyja/core/components/buttons/Buttons.kt",
            line=543,
            main_comment_body="Please fix the dialog state wiring",
            main_comment_author="reviewer",
            replies_count=1,
            last_reply_author="author",
            last_reply_body="Fixed in 343e2e9d7402d0afccfd35a9ecc8e6ea341031c6",
        )
    ]
    ctx.data["review_threads"] = [
        _make_thread(
            reply_body="Fixed in 343e2e9d7402d0afccfd35a9ecc8e6ea341031c6",
            path="freyja-core/src/main/kotlin/es/masorange/freyja/core/components/buttons/Buttons.kt",
            line=543,
            body="Please fix the dialog state wiring",
        )
    ]
    ctx.data["review_diff"] = (
        "diff --git a/freyja-core/src/main/kotlin/es/masorange/freyja/core/components/buttons/Buttons.kt "
        "b/freyja-core/src/main/kotlin/es/masorange/freyja/core/components/buttons/Buttons.kt\n"
        "@@ -541,3 +541,3 @@\n"
        "-fun ButtonDialog(dialogState: DialogState = rememberDialogState(false))\n"
        "+fun ButtonDialog(dialogState: DialogState)\n"
    )
    ctx.github.get_commit_review_context.return_value = ClientSuccess(
        data=ReferencedCommitContext(
            sha="343e2e9d7402d0afccfd35a9ecc8e6ea341031c6",
            abbreviated_sha="343e2e9",
            message="remove default state value",
            changed_files=["freyja-core/src/main/kotlin/.../BaseDialog.kt"],
            patch_excerpt="diff --git a/freyja-core/src/main/kotlin/.../BaseDialog.kt b/freyja-core/src/main/kotlin/.../BaseDialog.kt",
        ),
        message="ok",
    )

    result = build_thread_review_contexts(ctx)

    assert isinstance(result, Success)
    ctx.github.get_commit_review_context.assert_called_once_with(
        "343e2e9d7402d0afccfd35a9ecc8e6ea341031c6",
        repo_owner="forkuser",
        repo_name="fork-repo",
        max_files=3,
        max_patch_chars=4000,
    )


def test_build_thread_review_contexts_ignores_unavailable_referenced_commits():
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.github = Mock()
    ctx.data["thread_review_candidates"] = [
        ThreadReviewCandidate(
            thread_id="thread_123",
            path="src/main.py",
            line=42,
            main_comment_body="Please fix this",
            main_comment_author="reviewer",
            replies_count=1,
            last_reply_author="author",
            last_reply_body="Addressed in deadbee",
        )
    ]
    ctx.data["review_threads"] = [
        _make_thread(
            reply_body="Addressed in deadbee",
            path="src/main.py",
            line=42,
            body="Please fix this",
        )
    ]
    ctx.data["review_diff"] = "diff --git a/src/main.py b/src/main.py\n@@ -40,1 +40,1 @@\n-old\n+new\n"
    ctx.github.get_commit_review_context.return_value = ClientError(
        error_message="commit not found",
        error_code="API_ERROR",
    )

    result = build_thread_review_contexts(ctx)

    assert isinstance(result, Success)
    ctx.github.get_commit_review_context.assert_called_once_with(
        "deadbee",
        repo_owner=None,
        repo_name=None,
        max_files=3,
        max_patch_chars=4000,
    )
    contexts = ctx.data["thread_review_contexts"]
    assert contexts[0].referenced_commits == []


class _FakeFindingsAdapter:
    """Fake headless adapter recording every prompt it was asked to execute."""

    cli_name = SupportedCLI.CLAUDE

    def __init__(self):
        self.executed_prompts: list[str] = []

    supports_structured_output = False
    supports_tool_restriction = False
    supports_effort_control = False

    def is_available(self) -> bool:
        return True

    def execute(self, prompt: str, cwd=None, timeout=None, json_schema=None, disallowed_tools=None, effort=None) -> HeadlessResponse:
        self.executed_prompts.append(prompt)
        return HeadlessResponse(stdout="[]", stderr="", exit_code=0)


def _make_findings_batch(batch_id: str, files_chars: dict[str, int]) -> FocusContextBatch:
    return FocusContextBatch(
        batch_id=batch_id,
        files_context={
            path: FileContextEntry(
                path=path,
                read_mode=FileReadMode.HUNKS_ONLY,
                hunks=["x" * chars],
                approximate_chars=chars,
            )
            for path, chars in files_chars.items()
        },
    )


def test_ai_review_findings_splits_oversized_batch_via_prompt_budget_manager(monkeypatch):
    """
    review-batching-003 wiring test: `ai_review_findings` must route batch
    fitting through `PromptBudgetManager.fit_batch_to_budget()` so an
    over-budget batch gets split and both halves are still sent to the CLI.
    """
    fake_adapter = _FakeFindingsAdapter()
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [
        _make_findings_batch("batch_1", {"a.py": 3000, "b.py": 3000})
    ]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    # The oversized batch_1 must have been split into batch_1a/batch_1b, and
    # both halves sent to the adapter independently (2 CLI calls, not 1).
    assert len(fake_adapter.executed_prompts) == 2
    assert ctx.data["raw_findings"] == []
    assert ctx.data["ai_findings_failed"] is False


class _FakeFencedAdapter:
    """Fake headless adapter returning a markdown-fenced JSON array, once."""

    cli_name = SupportedCLI.CLAUDE
    supports_structured_output = False
    supports_tool_restriction = False
    supports_effort_control = False

    def __init__(self, stdout: str):
        self._stdout = stdout

    def is_available(self) -> bool:
        return True

    def execute(self, prompt: str, cwd=None, timeout=None, json_schema=None, disallowed_tools=None, effort=None) -> HeadlessResponse:
        return HeadlessResponse(stdout=self._stdout, stderr="", exit_code=0)


def test_ai_review_findings_parses_markdown_fenced_response(monkeypatch):
    """review-batching-006: ai_review_findings must go through the centralized
    `extract_json_payload()` helper, which strips markdown fences — not a
    bespoke inline parser."""
    fake_adapter = _FakeFencedAdapter('```json\n[{"title": "Bug"}]\n```')
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"a.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert ctx.data["raw_findings"] == [{"title": "Bug"}]
    assert ctx.data["ai_findings_failed"] is False


class _FakeSequentialAdapter:
    """Fake headless adapter returning one canned stdout per call, in order."""

    cli_name = SupportedCLI.CLAUDE
    supports_structured_output = False
    supports_tool_restriction = False
    supports_effort_control = False

    def __init__(self, stdouts: list[str]):
        self._stdouts = list(stdouts)
        self.calls: list[dict] = []

    def is_available(self) -> bool:
        return True

    def execute(self, prompt: str, cwd=None, timeout=None, json_schema=None, disallowed_tools=None, effort=None) -> HeadlessResponse:
        self.calls.append(
            {"prompt": prompt, "cwd": cwd, "timeout": timeout, "disallowed_tools": disallowed_tools, "effort": effort}
        )
        stdout = self._stdouts[len(self.calls) - 1]
        return HeadlessResponse(stdout=stdout, stderr="", exit_code=0)


def test_ai_review_findings_recovers_via_reformat_retry(monkeypatch):
    """review-batching-007: when the model returns prose instead of JSON
    (exit_code 0), ai_review_findings must retry once, asking the same CLI to
    reformat its own previous output, using a short timeout distinct from the
    300s analysis timeout — and recover the findings if the retry succeeds."""
    fake_adapter = _FakeSequentialAdapter(
        ["Reported one finding: fix the null check.", '```json\n[{"title": "Bug"}]\n```']
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"a.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert ctx.data["raw_findings"] == [{"title": "Bug"}]
    assert ctx.data["ai_findings_failed"] is False
    assert len(fake_adapter.calls) == 2
    assert fake_adapter.calls[1]["timeout"] == 45
    assert fake_adapter.calls[1]["timeout"] != fake_adapter.calls[0]["timeout"]


def test_ai_review_findings_marks_batch_failed_when_reformat_retry_also_fails(monkeypatch):
    fake_adapter = _FakeSequentialAdapter(
        ["Reported one finding: fix the null check.", "Still no JSON here, sorry."]
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"a.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    # The only batch failed, so the whole step must fail visibly (0/1 produced output).
    assert isinstance(result, Error)
    assert len(fake_adapter.calls) == 2
    assert ctx.data["ai_findings_failed"] is True
    assert ctx.data["raw_findings"] == []


def test_ai_review_findings_partial_batch_failure_still_succeeds_with_flag(monkeypatch):
    """One batch fails parse (main + retry), the other returns findings: the step
    succeeds but ai_findings_failed must be True so the outcome isn't presented
    as a fully clean review."""
    from titan_plugin_github.models.review_profile_models import ReviewProfile

    fake_adapter = _FakeSequentialAdapter(
        [
            "Reported one finding: fix the null check.",  # batch_1 main call (prose)
            "Still no JSON here, sorry.",  # batch_1 reformat retry
            '[{"title": "Bug"}]',  # batch_2 main call
        ]
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    # The canned-stdout sequence assumes batch order — pin the pool to 1.
    ctx.data["review_profile"] = ReviewProfile(findings_batch_concurrency=1)
    ctx.data["review_context_batches"] = [
        _make_findings_batch("batch_1", {"a.py": 100}),
        _make_findings_batch("batch_2", {"b.py": 100}),
    ]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert ctx.data["raw_findings"] == [{"title": "Bug"}]
    assert ctx.data["ai_findings_failed"] is True


class _FakeFailingCLIAdapter:
    """Fake headless adapter whose every call fails with a non-zero exit code."""

    cli_name = SupportedCLI.CLAUDE
    supports_structured_output = False
    supports_tool_restriction = False
    supports_effort_control = False

    def __init__(self, exit_code: int = 1):
        self._exit_code = exit_code
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def execute(self, prompt: str, cwd=None, timeout=None, json_schema=None, disallowed_tools=None, effort=None) -> HeadlessResponse:
        self.calls += 1
        return HeadlessResponse(stdout="", stderr="credit balance too low", exit_code=self._exit_code)


def test_ai_review_findings_returns_error_when_all_batches_fail(monkeypatch):
    """review-quality-005: when every batch fails (e.g. headless CLI without credits,
    observed live 2026-07-31), the step must NOT report plain Success — a total AI
    failure was indistinguishable from a clean review. raw_findings stays published
    (empty) so downstream steps and worktree cleanup still run via on_error: continue."""
    fake_adapter = _FakeFailingCLIAdapter(exit_code=1)
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [
        _make_findings_batch("batch_1", {"a.py": 100}),
        _make_findings_batch("batch_2", {"b.py": 100}),
    ]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    assert isinstance(result, Error)
    assert "0/2" in result.message
    assert fake_adapter.calls == 2
    assert ctx.data["raw_findings"] == []
    assert ctx.data["ai_findings_failed"] is True


class _FakeStructuredSequentialAdapter:
    """Fake structured-output adapter returning one canned stdout per call, in order."""

    cli_name = SupportedCLI.CLAUDE
    supports_structured_output = True
    supports_tool_restriction = True
    supports_effort_control = True

    def __init__(self, stdouts: list[str]):
        self._stdouts = list(stdouts)
        self.calls: list[dict] = []

    def is_available(self) -> bool:
        return True

    def execute(self, prompt: str, cwd=None, timeout=None, json_schema=None, disallowed_tools=None, effort=None) -> HeadlessResponse:
        self.calls.append({"prompt": prompt, "timeout": timeout, "json_schema": json_schema})
        stdout = self._stdouts[len(self.calls) - 1]
        return HeadlessResponse(stdout=stdout, stderr="", exit_code=0)


def test_ai_review_findings_non_list_payload_goes_through_reformat_retry(monkeypatch):
    """review-quality-005: a structured success whose findings payload isn't a list
    (e.g. a dict) used to hit `case ClientSuccess(): pass` and vanish — no failure
    flag, no batch result rendered. It must go through the reformat-retry path and
    recover when the retry returns a proper list."""
    fake_adapter = _FakeStructuredSequentialAdapter(
        [
            '{"findings": {"title": "Bug"}}',  # main call: dict payload, not a list
            '{"findings": [{"title": "Bug"}]}',  # reformat retry: proper list
        ]
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"a.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert len(fake_adapter.calls) == 2
    assert ctx.data["raw_findings"] == [{"title": "Bug"}]
    assert ctx.data["ai_findings_failed"] is False


def test_ai_review_findings_non_list_payload_marks_failed_when_retry_also_non_list(monkeypatch):
    fake_adapter = _FakeStructuredSequentialAdapter(
        [
            '{"findings": {"title": "Bug"}}',  # main call: dict payload
            '{"findings": {"title": "Bug"}}',  # retry: still a dict
        ]
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"a.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    # Single batch, non-list payload twice: batch failed, so 0/1 → step fails visibly.
    assert isinstance(result, Error)
    assert len(fake_adapter.calls) == 2
    assert ctx.data["ai_findings_failed"] is True
    assert ctx.data["raw_findings"] == []


class _FakeStructuredOutputAdapter:
    """Fake adapter simulating a CLI that supports --json-schema (like Claude)."""

    cli_name = SupportedCLI.CLAUDE
    supports_structured_output = True
    supports_tool_restriction = True
    supports_effort_control = True

    def __init__(self, stdout: str):
        self._stdout = stdout
        self.calls: list[dict] = []

    def is_available(self) -> bool:
        return True

    def execute(self, prompt: str, cwd=None, timeout=None, json_schema=None, disallowed_tools=None, effort=None) -> HeadlessResponse:
        self.calls.append(
            {
                "prompt": prompt,
                "cwd": cwd,
                "timeout": timeout,
                "json_schema": json_schema,
                "disallowed_tools": disallowed_tools,
                "effort": effort,
            }
        )
        return HeadlessResponse(stdout=self._stdout, stderr="", exit_code=0)


def test_ai_review_findings_uses_structured_output_when_supported(monkeypatch):
    """review-batching-008: when the adapter supports structured output, ai_review_findings
    must request it (json_schema kwarg) and unwrap the {"findings": [...]} envelope,
    instead of parsing a bare JSON array out of free text."""
    fake_adapter = _FakeStructuredOutputAdapter('{"findings": [{"title": "Bug"}]}')
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"a.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert ctx.data["raw_findings"] == [{"title": "Bug"}]
    assert ctx.data["ai_findings_failed"] is False
    assert fake_adapter.calls[0]["json_schema"] is not None
    assert fake_adapter.calls[0]["json_schema"]["required"] == ["findings"]


def test_ai_review_findings_structured_output_retry_also_requests_schema(monkeypatch):
    """If the model doesn't call the structured-output tool on the first try (rare), the
    reformat retry must still request structured output — not silently downgrade to
    free-text parsing."""
    fake_adapter = _FakeStructuredOutputAdapter("I won't call that tool.")
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"a.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    # The only batch failed even after the retry, so the step fails (0/1 produced output).
    assert isinstance(result, Error)
    assert len(fake_adapter.calls) == 2
    assert fake_adapter.calls[1]["json_schema"] is not None
    assert ctx.data["ai_findings_failed"] is True


def test_ai_review_findings_restricts_tools_when_supported(monkeypatch):
    """O-003/D-011 fix: when the adapter supports tool restriction, ai_review_findings must
    deny Bash (and the other unneeded tools) so the CLI can't explore far beyond the batch's
    worktree_reference files — Read/Grep/Glob stay implicitly available since they're not
    in the denylist."""
    from titan_plugin_github.operations.findings_operations import FINDINGS_DISALLOWED_TOOLS

    fake_adapter = _FakeStructuredOutputAdapter('{"findings": [{"title": "Bug"}]}')
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"a.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert fake_adapter.calls[0]["disallowed_tools"] == list(FINDINGS_DISALLOWED_TOOLS)


def test_ai_review_findings_omits_disallowed_tools_when_unsupported(monkeypatch):
    """Adapters without tool-restriction support (Codex, Gemini) must not receive a
    disallowed_tools list — the step must not assume the capability is universal."""
    fake_adapter = _FakeSequentialAdapter(['[{"title": "Bug"}]'])
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"a.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert fake_adapter.calls[0]["disallowed_tools"] is None


def test_ai_review_findings_reformat_retry_also_restricts_tools(monkeypatch):
    """The reformat retry reuses the same adapter for a lighter-weight call with no
    exploration need at all — it must still receive the same tool restriction."""
    from titan_plugin_github.operations.findings_operations import FINDINGS_DISALLOWED_TOOLS

    fake_adapter = _FakeStructuredOutputAdapter("I won't call that tool.")
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"a.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    # The only batch failed even after the retry, so the step fails (0/1 produced output).
    assert isinstance(result, Error)
    assert len(fake_adapter.calls) == 2
    assert fake_adapter.calls[1]["disallowed_tools"] == list(FINDINGS_DISALLOWED_TOOLS)


def _make_worktree_reference_batch(batch_id: str, path: str) -> FocusContextBatch:
    return FocusContextBatch(
        batch_id=batch_id,
        files_context={
            path: FileContextEntry(
                path=path,
                read_mode=FileReadMode.WORKTREE_REFERENCE,
                worktree_reference=True,
                review_hint="Read this file from the worktree.",
                approximate_chars=100,
            )
        },
    )


def test_ai_review_findings_caps_effort_for_worktree_reference_batch(monkeypatch):
    """O-003 fix: a real replay showed removing Bash alone didn't reduce duration — Claude
    still took ~330s regardless of tool. Capping effort at FINDINGS_WORKTREE_REFERENCE_EFFORT
    cut that to ~170s in the same replay while still finding a genuine bug an independent CLI
    also found, so ai_review_findings must request it for worktree_reference batches."""
    from titan_plugin_github.operations.findings_operations import FINDINGS_WORKTREE_REFERENCE_EFFORT

    fake_adapter = _FakeStructuredOutputAdapter('{"findings": []}')
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [_make_worktree_reference_batch("batch_1", "HomeScreen.kt")]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert fake_adapter.calls[0]["effort"] == FINDINGS_WORKTREE_REFERENCE_EFFORT


def test_ai_review_findings_omits_effort_when_no_worktree_reference(monkeypatch):
    """A batch with only inline file content has no reason to explore, so it must keep the
    adapter's default effort rather than unconditionally capping every findings call."""
    fake_adapter = _FakeStructuredOutputAdapter('{"findings": []}')
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"a.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=6000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert fake_adapter.calls[0]["effort"] is None


def test_ai_thread_resolution_parses_markdown_fenced_response(monkeypatch):
    """review-batching-006: ai_thread_resolution used to hand-roll its own fence
    stripping and JSON-slice extraction. It must now share the same
    `extract_json_payload()` helper as ai_review_findings/ai_review_plan."""
    fake_adapter = _FakeFencedAdapter('```json\n[{"thread_id": "t1", "decision": "resolved"}]\n```')
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["thread_review_contexts"] = [
        ThreadReviewContext(
            thread_id="t1",
            comment_id=1,
            main_comment_body="Please fix this",
            main_comment_author="alex",
        )
    ]
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_thread_resolution(ctx)

    assert isinstance(result, Success)
    assert ctx.data["raw_thread_decisions"] == [{"thread_id": "t1", "decision": "resolved"}]


def test_ai_thread_resolution_falls_back_to_empty_decisions_on_parse_failure(monkeypatch):
    fake_adapter = _FakeFencedAdapter("I could not analyse these threads.")
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["thread_review_contexts"] = [
        ThreadReviewContext(
            thread_id="t1",
            comment_id=1,
            main_comment_body="Please fix this",
            main_comment_author="alex",
        )
    ]
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"

    result = ai_thread_resolution(ctx)

    assert isinstance(result, Success)
    assert ctx.data["raw_thread_decisions"] == []


# ---------------------------------------------------------------------------
# File-read access guard: the fallback root is the user's own checkout, which is
# usually on a different branch than the PR head.
# ---------------------------------------------------------------------------

_HEAD_SHA = "a" * 40
_OTHER_SHA = "b" * 40


def _read_access_ctx(*, head_sha=_HEAD_SHA, checkout_sha=_HEAD_SHA, dirty=False, with_git=True):
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_commit_sha"] = head_sha
    if with_git:
        ctx.git = Mock()
        ctx.git.get_current_commit.return_value = ClientSuccess(data=checkout_sha, message="ok")
        ctx.git.has_uncommitted_changes.return_value = ClientSuccess(data=dirty, message="ok")
    else:
        ctx.git = None
    return ctx


def test_file_read_access_trusts_worktree_without_querying_git():
    ctx = _read_access_ctx(checkout_sha=_OTHER_SHA)

    access = code_review_steps._resolve_file_read_access(ctx, "/tmp/titan-review-1")

    assert access.allowed is True
    assert access.source == "worktree"
    ctx.git.get_current_commit.assert_not_called()


def test_file_read_access_allows_clean_checkout_at_pr_head():
    ctx = _read_access_ctx()

    access = code_review_steps._resolve_file_read_access(ctx, None)

    assert access.allowed is True
    assert access.source == "checkout"


def test_file_read_access_blocks_checkout_on_another_branch():
    """The failure mode: create_worktree failed (on_error: continue) and the user is
    sitting on an unrelated branch."""
    ctx = _read_access_ctx(checkout_sha=_OTHER_SHA)

    access = code_review_steps._resolve_file_read_access(ctx, None)

    assert access.allowed is False


def test_file_read_access_blocks_dirty_checkout():
    ctx = _read_access_ctx(dirty=True)

    access = code_review_steps._resolve_file_read_access(ctx, None)

    assert access.allowed is False


def test_file_read_access_blocks_when_git_queries_fail():
    ctx = _read_access_ctx()
    ctx.git.get_current_commit.return_value = ClientError(
        error_message="not a repo", error_code="GIT_ERROR"
    )

    access = code_review_steps._resolve_file_read_access(ctx, None)

    assert access.allowed is False


def test_file_read_access_blocks_without_git_client():
    ctx = _read_access_ctx(with_git=False)

    access = code_review_steps._resolve_file_read_access(ctx, None)

    assert access.allowed is False


def test_file_read_access_blocks_when_head_sha_unknown():
    ctx = _read_access_ctx(head_sha="")

    access = code_review_steps._resolve_file_read_access(ctx, None)

    assert access.allowed is False


# ---------------------------------------------------------------------------
# Submit-time head SHA re-check: the bundle SHA is minutes old by then
# ---------------------------------------------------------------------------


def _drift_ctx(current_sha_result):
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.github = Mock()
    ctx.github.get_pr_commit_sha.return_value = current_sha_result
    return ctx


def test_submit_sha_drift_detected_when_pr_was_pushed_to():
    ctx = _drift_ctx(ClientSuccess(data="b" * 40, message="ok"))

    drift = code_review_steps._detect_submit_time_sha_drift(ctx, 123, "a" * 40)

    assert drift.drifted is True
    assert drift.current_sha == "b" * 40


def test_submit_sha_no_drift_when_head_is_unchanged():
    ctx = _drift_ctx(ClientSuccess(data="a" * 40, message="ok"))

    drift = code_review_steps._detect_submit_time_sha_drift(ctx, 123, "a" * 40)

    assert drift.drifted is False


def test_submit_sha_recheck_failure_does_not_block_the_submission():
    """The publish gate already validates lines against the diff, so a failed
    re-check must not degrade or cancel an otherwise valid review."""
    ctx = _drift_ctx(ClientError(error_message="api down", error_code="GH_ERROR"))

    drift = code_review_steps._detect_submit_time_sha_drift(ctx, 123, "a" * 40)

    assert drift.drifted is False


def test_resolve_drift_changed_files_returns_pushed_paths():
    """On drift, the push's touched files come from a local diff so only their
    comments degrade — after a fetch, since the new head postdates the review's own."""
    from titan_plugin_github.operations.review_action_operations import detect_head_sha_drift

    ctx = WorkflowContext()
    ctx.git = Mock()
    ctx.git.fetch.return_value = ClientSuccess(data=None, message="ok")
    ctx.git.get_changed_files.return_value = ClientSuccess(
        data=["src/touched.py"], message="ok"
    )
    drift = detect_head_sha_drift("a" * 40, "b" * 40)

    paths = code_review_steps._resolve_drift_changed_files(ctx, drift)

    assert paths == {"src/touched.py"}
    ctx.git.fetch.assert_called_once()
    ctx.git.get_changed_files.assert_called_once_with("a" * 40, "b" * 40)


def test_resolve_drift_changed_files_unknowable_returns_none():
    """git unavailable or failing → None, so the caller degrades everything
    (never publishes stale anchors on a hunch)."""
    from titan_plugin_github.operations.review_action_operations import detect_head_sha_drift

    drift = detect_head_sha_drift("a" * 40, "b" * 40)

    no_git_ctx = WorkflowContext()
    no_git_ctx.git = None
    assert code_review_steps._resolve_drift_changed_files(no_git_ctx, drift) is None

    failing_ctx = WorkflowContext()
    failing_ctx.git = Mock()
    failing_ctx.git.fetch.return_value = ClientSuccess(data=None, message="ok")
    failing_ctx.git.get_changed_files.return_value = ClientError(
        error_message="bad object", error_code="DIFF_ERROR"
    )
    assert code_review_steps._resolve_drift_changed_files(failing_ctx, drift) is None


def test_submit_sha_drift_ignores_surrounding_whitespace():
    ctx = _drift_ctx(ClientSuccess(data=f"  {'a' * 40}\n", message="ok"))

    drift = code_review_steps._detect_submit_time_sha_drift(ctx, 123, "a" * 40)

    assert drift.drifted is False


# ============================================================================
# verify_findings (review-quality-003)
# ============================================================================


def _make_finding_model(
    title: str = "Null check missing",
    severity: FindingSeverity = FindingSeverity.IMPORTANT,
    path: str = "a.py",
) -> Finding:
    return Finding(
        severity=severity,
        category="error_handling",
        path=path,
        line=10,
        title=title,
        why="The value may be None",
        evidence="value.method()",
        suggested_comment="Add a null check",
    )


def _verify_ctx(findings: list, adapter_stdout: str | None = None) -> WorkflowContext:
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["deduped_findings"] = findings
    ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"a.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=20000,
        max_comment_entries=5,
    )
    # The pass ships disabled by default (it has never refuted a real finding);
    # these tests exercise the step itself, so they opt in explicitly.
    ctx.data["review_profile"] = ReviewProfile(findings_verification_enabled=True)
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"
    return ctx


def test_verify_findings_drops_refuted_finding(monkeypatch):
    """review-quality-003: a finding the verifier refutes with evidence is removed
    from deduped_findings before the human gate, and published as refuted."""
    refuted = _make_finding_model("False positive")
    confirmed = _make_finding_model("Real bug")
    stdout = '{"verdicts": [{"index": 0, "verdict": "refuted", "reasoning": "check exists at line 12"}, {"index": 1, "verdict": "confirmed", "reasoning": "holds"}]}'
    fake_adapter = _FakeStructuredOutputAdapter(stdout)
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = _verify_ctx([refuted, confirmed])
    result = verify_findings(ctx)

    assert isinstance(result, Success)
    assert ctx.data["deduped_findings"] == [confirmed]
    assert ctx.data["refuted_findings"] == [refuted]
    # Verification must run at low effort with the verdicts schema (D-002/D-003).
    assert fake_adapter.calls[0]["effort"] == "low"
    assert fake_adapter.calls[0]["json_schema"]["required"] == ["verdicts"]


def test_verify_findings_fails_open_on_cli_failure(monkeypatch):
    finding = _make_finding_model()
    fake_adapter = _FakeFailingCLIAdapter(exit_code=1)
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = _verify_ctx([finding])
    result = verify_findings(ctx)

    assert isinstance(result, Skip)
    assert ctx.data["deduped_findings"] == [finding]


def test_verify_findings_fails_open_on_unparseable_response(monkeypatch):
    finding = _make_finding_model()
    fake_adapter = _FakeStructuredOutputAdapter("I cannot judge these findings, sorry.")
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = _verify_ctx([finding])
    result = verify_findings(ctx)

    assert isinstance(result, Skip)
    assert ctx.data["deduped_findings"] == [finding]


def test_verify_findings_disabled_by_default(monkeypatch):
    """The pass ships OFF: across every observed real review it refuted nothing,
    so by default it only adds latency. Projects opt in via profile.yaml."""
    finding = _make_finding_model()
    fake_adapter = _FakeStructuredOutputAdapter("should never be called")
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = _verify_ctx([finding])
    ctx.data["review_profile"] = ReviewProfile()
    result = verify_findings(ctx)

    assert isinstance(result, Skip)
    assert fake_adapter.calls == []


def test_verify_findings_skips_when_profile_disables_it(monkeypatch):
    finding = _make_finding_model()
    fake_adapter = _FakeStructuredOutputAdapter("should never be called")
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = _verify_ctx([finding])
    ctx.data["review_profile"] = ReviewProfile(findings_verification_enabled=False)
    result = verify_findings(ctx)

    assert isinstance(result, Skip)
    assert fake_adapter.calls == []
    assert ctx.data["deduped_findings"] == [finding]


def test_verify_findings_skips_nit_only_findings(monkeypatch):
    nit = _make_finding_model("Style nit", severity=FindingSeverity.NIT)
    fake_adapter = _FakeStructuredOutputAdapter("should never be called")
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = _verify_ctx([nit])
    result = verify_findings(ctx)

    assert isinstance(result, Skip)
    assert fake_adapter.calls == []
    assert ctx.data["deduped_findings"] == [nit]


def test_verify_findings_fails_open_when_prompt_over_budget(monkeypatch):
    finding = _make_finding_model()
    fake_adapter = _FakeStructuredOutputAdapter("should never be called")
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = _verify_ctx([finding])
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=100,
        max_comment_entries=5,
    )
    result = verify_findings(ctx)

    assert isinstance(result, Skip)
    assert fake_adapter.calls == []
    assert ctx.data["deduped_findings"] == [finding]


# ============================================================================
# ai_review_findings concurrency (review-quality-006)
# ============================================================================


class _FakeConcurrencyTrackingAdapter:
    """Fake adapter that records how many executes overlap in flight."""

    cli_name = SupportedCLI.CLAUDE
    supports_structured_output = False
    supports_tool_restriction = False
    supports_effort_control = False

    def __init__(self, stdout: str = "[]", block_until: int | None = None):
        self._stdout = stdout
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0
        self.calls = 0
        # When set, every call waits until `block_until` calls are in flight —
        # proves genuine overlap (deadlocks under a sequential executor).
        self._barrier = threading.Barrier(block_until, timeout=10) if block_until else None

    def is_available(self) -> bool:
        return True

    def execute(self, prompt: str, cwd=None, timeout=None, json_schema=None, disallowed_tools=None, effort=None) -> HeadlessResponse:
        with self._lock:
            self.calls += 1
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            if self._barrier:
                self._barrier.wait()
            return HeadlessResponse(stdout=self._stdout, stderr="", exit_code=0)
        finally:
            with self._lock:
                self._in_flight -= 1


def _concurrency_ctx(batch_count: int, concurrency: int) -> WorkflowContext:
    from titan_plugin_github.models.review_profile_models import ReviewProfile

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_profile"] = ReviewProfile(findings_batch_concurrency=concurrency)
    ctx.data["review_context_batches"] = [
        _make_findings_batch(f"batch_{i}", {f"f{i}.py": 100}) for i in range(batch_count)
    ]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=20000,
        max_comment_entries=5,
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"
    return ctx


def test_ai_review_findings_runs_batches_concurrently(monkeypatch):
    """review-quality-006: with findings_batch_concurrency=2, two batches must be
    in flight at the same time (the barrier only releases when both arrive — this
    test deadlocks/times out under a sequential executor)."""
    fake_adapter = _FakeConcurrencyTrackingAdapter(stdout='[{"title": "Bug"}]', block_until=2)
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = _concurrency_ctx(batch_count=2, concurrency=2)
    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert fake_adapter.max_in_flight == 2
    assert ctx.data["raw_findings"] == [{"title": "Bug"}, {"title": "Bug"}]
    assert ctx.data["ai_findings_failed"] is False


def test_ai_review_findings_concurrency_one_stays_sequential(monkeypatch):
    fake_adapter = _FakeConcurrencyTrackingAdapter(stdout="[]")
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = _concurrency_ctx(batch_count=3, concurrency=1)
    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert fake_adapter.calls == 3
    assert fake_adapter.max_in_flight == 1


def test_ai_review_findings_pool_never_exceeds_configured_concurrency(monkeypatch):
    fake_adapter = _FakeConcurrencyTrackingAdapter(stdout="[]")
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = _concurrency_ctx(batch_count=6, concurrency=2)
    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert fake_adapter.calls == 6
    assert fake_adapter.max_in_flight <= 2


def test_ai_review_findings_worker_crash_marks_batch_failed_not_step_crash(monkeypatch):
    """An adapter exception inside a worker must degrade to a failed batch (visible),
    not crash the whole step."""

    class _ExplodingAdapter:
        cli_name = SupportedCLI.CLAUDE
        supports_structured_output = False
        supports_tool_restriction = False
        supports_effort_control = False

        def is_available(self) -> bool:
            return True

        def execute(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: _ExplodingAdapter())

    ctx = _concurrency_ctx(batch_count=1, concurrency=2)
    result = ai_review_findings(ctx)

    # Single batch crashed → 0/1 produced output → visible Error (review-quality-005).
    assert isinstance(result, Error)
    assert ctx.data["raw_findings"] == []
    assert ctx.data["ai_findings_failed"] is True


# ============================================================================
# ai_review_findings empty-findings rescue (review-quality-007)
# ============================================================================


def _rescue_ctx(adapter_stdouts: list[str]) -> tuple[WorkflowContext, "_FakeSequentialAdapter"]:
    fake_adapter = _FakeSequentialAdapter(adapter_stdouts)
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_profile"] = ReviewProfile(findings_batch_concurrency=1)
    ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"a.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=20000,
        max_comment_entries=5,
        suspicious_empty_findings=True,
    )
    ctx.data["review_candidates"] = [
        ScoredReviewCandidate(
            path="border.py",
            score=3,
            priority=FileReviewPriority.LOW,
            suggested_read_mode=FileReadMode.HUNKS_ONLY,
        )
    ]
    ctx.data["review_diff"] = (
        "diff --git a/border.py b/border.py\n"
        "index 111..222 100644\n"
        "--- a/border.py\n"
        "+++ b/border.py\n"
        "@@ -1,2 +1,3 @@\n"
        " context\n"
        "+added line\n"
        " context\n"
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"
    return ctx, fake_adapter


def test_ai_review_findings_runs_rescue_batch_on_suspicious_empty(monkeypatch):
    """review-quality-007: zero findings + suspicious_empty_findings must trigger ONE
    extra rescue batch over borderline unreviewed files — not just a dim line."""
    ctx, fake_adapter = _rescue_ctx(
        [
            "[]",  # batch_1: clean review, no findings
            '[{"title": "Rescued bug", "path": "border.py"}]',  # rescue batch
        ]
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert len(fake_adapter.calls) == 2
    assert "border.py" in fake_adapter.calls[1]["prompt"]
    assert ctx.data["raw_findings"] == [{"title": "Rescued bug", "path": "border.py"}]
    assert ctx.data["ai_findings_failed"] is False


def test_ai_review_findings_rescue_failure_does_not_fail_the_review(monkeypatch):
    """The rescue pass is best-effort: if it fails, the review stays a clean Success
    (the main batches DID complete with zero findings)."""
    ctx, fake_adapter = _rescue_ctx(
        [
            "[]",  # batch_1: clean
            "no json from the rescue call",  # rescue main call
            "still no json",  # rescue reformat retry
        ]
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert ctx.data["raw_findings"] == []
    assert ctx.data["ai_findings_failed"] is False


def test_ai_review_findings_no_rescue_when_findings_exist(monkeypatch):
    ctx, fake_adapter = _rescue_ctx(['[{"title": "Bug"}]'])
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert len(fake_adapter.calls) == 1


def test_ai_review_findings_no_rescue_when_not_suspicious(monkeypatch):
    ctx, fake_adapter = _rescue_ctx(["[]"])
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=20000,
        max_comment_entries=5,
        suspicious_empty_findings=False,
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert len(fake_adapter.calls) == 1


# ============================================================================
# ai_review_findings cross-file synthesis (review-quality-004)
# ============================================================================


def _synthesis_diff(line: str = "added line") -> str:
    def _file_diff(path: str) -> str:
        return (
            f"diff --git a/{path} b/{path}\n"
            "index 111..222 100644\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            "@@ -1,2 +1,3 @@\n"
            " context\n"
            f"+{line}\n"
            " context\n"
        )

    return _file_diff("a.py") + _file_diff("b.py")


def _synthesis_ctx(
    adapter_stdouts: list[str],
    *,
    enabled: bool = True,
    batch_files: list[dict[str, int]] | None = None,
    diff: str | None = None,
) -> tuple[WorkflowContext, "_FakeSequentialAdapter"]:
    fake_adapter = _FakeSequentialAdapter(adapter_stdouts)
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_profile"] = ReviewProfile(
        findings_batch_concurrency=1, findings_synthesis_enabled=enabled
    )
    files = batch_files if batch_files is not None else [{"a.py": 100}, {"b.py": 100}]
    ctx.data["review_context_batches"] = [
        _make_findings_batch(f"batch_{index + 1}", file_chars)
        for index, file_chars in enumerate(files)
    ]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=20000,
        max_comment_entries=5,
        suspicious_empty_findings=False,
    )
    ctx.data["review_diff"] = diff if diff is not None else _synthesis_diff()
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"
    return ctx, fake_adapter


def test_ai_review_findings_runs_synthesis_when_enabled_and_multi_file(monkeypatch):
    """review-quality-004: with the profile flag on and >1 focus file, one extra
    cross-file synthesis batch runs after the per-file batches — even when the
    per-file batches already produced findings (unlike the 007 rescue)."""
    ctx, fake_adapter = _synthesis_ctx(
        [
            '[{"title": "Bug in a", "path": "a.py", "line": 5}]',  # batch_1
            "[]",  # batch_2
            '[{"title": "Contract mismatch", "path": "b.py", "line": 2}]',  # synthesis
        ]
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert len(fake_adapter.calls) == 3
    synthesis_prompt = fake_adapter.calls[2]["prompt"]
    assert "cross-file inconsistencies" in synthesis_prompt
    assert "a.py" in synthesis_prompt and "b.py" in synthesis_prompt
    assert ctx.data["raw_findings"] == [
        {"title": "Bug in a", "path": "a.py", "line": 5},
        {"title": "Contract mismatch", "path": "b.py", "line": 2},
    ]
    assert ctx.data["ai_findings_failed"] is False


def test_ai_review_findings_synthesis_disabled_by_default(monkeypatch):
    ctx, fake_adapter = _synthesis_ctx(["[]", "[]"], enabled=False)
    # Same as the default profile: the flag is opt-in (D-002 token mandate).
    assert ReviewProfile().findings_synthesis_enabled is False
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert len(fake_adapter.calls) == 2


def test_ai_review_findings_no_synthesis_single_focus_file(monkeypatch):
    ctx, fake_adapter = _synthesis_ctx(["[]"], batch_files=[{"a.py": 100}])
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert len(fake_adapter.calls) == 1


def test_ai_review_findings_synthesis_skipped_over_budget(monkeypatch):
    """Over-budget synthesis skips silently — no split/degrade machinery, no 3rd call."""
    # Big diff hunks blow the synthesis prompt past the budget, while the per-file
    # batches (100 chars each) still fit comfortably.
    ctx, fake_adapter = _synthesis_ctx(
        ["[]", "[]"], diff=_synthesis_diff(line="z" * 15000)
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert len(fake_adapter.calls) == 2
    assert ctx.data["ai_findings_failed"] is False


def test_ai_review_findings_synthesis_failure_is_best_effort(monkeypatch):
    """A failed synthesis call must not mark an otherwise-successful review as failed."""
    ctx, fake_adapter = _synthesis_ctx(
        [
            '[{"title": "Bug in a", "path": "a.py", "line": 5}]',  # batch_1
            "[]",  # batch_2
            "no json from the synthesis call",  # synthesis main call
            "still no json",  # synthesis reformat retry
        ]
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert ctx.data["raw_findings"] == [{"title": "Bug in a", "path": "a.py", "line": 5}]
    assert ctx.data["ai_findings_failed"] is False


def test_ai_review_findings_synthesis_dedupes_against_per_file_findings(monkeypatch):
    """Synthesis near-duplicates of per-file findings are dropped before aggregation;
    only genuinely new cross-file findings are added."""
    ctx, fake_adapter = _synthesis_ctx(
        [
            '[{"title": "Bug in a", "path": "a.py", "line": 5}]',  # batch_1
            "[]",  # batch_2
            (
                '[{"title": "Bug in a", "path": "a.py", "line": 7},'
                ' {"title": "Contract mismatch", "path": "b.py", "line": 2}]'
            ),  # synthesis: near-dup (same path, line within 5, same title) + new
        ]
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert ctx.data["raw_findings"] == [
        {"title": "Bug in a", "path": "a.py", "line": 5},
        {"title": "Contract mismatch", "path": "b.py", "line": 2},
    ]


# ============================================================================
# Fixes from the 2026-08-03 validation-run findings
# ============================================================================


def test_verify_findings_mixed_nit_and_non_nit_index_remapping(monkeypatch):
    """Verdict indices address the FILTERED (non-nit) list. With nits mixed in, a
    refutation of filtered-index 0 must drop the right non-nit finding while every
    nit rides through untouched."""
    nit_first = _make_finding_model("Style nit", severity=FindingSeverity.NIT)
    false_positive = _make_finding_model("False positive")
    real_bug = _make_finding_model("Real bug")
    nit_last = _make_finding_model("Another nit", severity=FindingSeverity.NIT)
    stdout = (
        '{"verdicts": [{"index": 0, "verdict": "refuted", "reasoning": "check exists"},'
        ' {"index": 1, "verdict": "confirmed", "reasoning": "holds"}]}'
    )
    fake_adapter = _FakeStructuredOutputAdapter(stdout)
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = _verify_ctx([nit_first, false_positive, real_bug, nit_last])
    result = verify_findings(ctx)

    assert isinstance(result, Success)
    # Index 0 of the filtered list is "False positive", NOT the leading nit.
    assert ctx.data["refuted_findings"] == [false_positive]
    assert set(f.title for f in ctx.data["deduped_findings"]) == {
        "Style nit",
        "Real bug",
        "Another nit",
    }
    # Only the 2 non-nit findings were sent to the verifier.
    prompt = fake_adapter.calls[0]["prompt"]
    assert "Style nit" not in prompt
    assert "False positive" in prompt


def test_verify_findings_refutation_ignored_when_path_has_no_code(monkeypatch):
    """A refutation for a finding whose path has no hunks in any batch is ignored:
    the model never saw that code, so its contradiction is worthless."""
    orphan = _make_finding_model("Orphan finding", path="not_in_batches.py")
    stdout = '{"verdicts": [{"index": 0, "verdict": "refuted", "reasoning": "no such code"}]}'
    fake_adapter = _FakeStructuredOutputAdapter(stdout)
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    ctx = _verify_ctx([orphan])
    result = verify_findings(ctx)

    assert isinstance(result, Success)
    assert ctx.data["deduped_findings"] == [orphan]
    assert ctx.data["refuted_findings"] == []


def _three_file_diff() -> str:
    def _file_diff(path: str) -> str:
        return (
            f"diff --git a/{path} b/{path}\n"
            "index 111..222 100644\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            "@@ -1,2 +1,3 @@\n"
            " context\n"
            "+added line\n"
            " context\n"
        )

    return _file_diff("a.py") + _file_diff("b.py") + _file_diff("c.py")


def test_ai_review_findings_synthesis_excludes_failed_batches_paths(monkeypatch):
    """A failed batch's files were NOT reviewed — the synthesis prompt must not
    include them under instructions claiming their single-file issues were already
    covered (that would suppress findings nobody ever looked for)."""
    ctx, fake_adapter = _synthesis_ctx(
        [
            "[]",  # batch_1 (a.py) ok
            "[]",  # batch_2 (b.py) ok
            "no json from batch_3",  # batch_3 (c.py) main call
            "still no json",  # batch_3 reformat retry -> failed
            "[]",  # synthesis over a.py + b.py only
        ],
        batch_files=[{"a.py": 100}, {"b.py": 100}, {"c.py": 100}],
        diff=_three_file_diff(),
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert len(fake_adapter.calls) == 5
    synthesis_prompt = fake_adapter.calls[4]["prompt"]
    assert "### a.py" in synthesis_prompt
    assert "### b.py" in synthesis_prompt
    assert "c.py" not in synthesis_prompt


def test_ai_review_findings_no_synthesis_when_only_one_batch_succeeded(monkeypatch):
    """With 2 focus files but only 1 reviewed (other batch failed), synthesis is
    skipped: there is nothing cross-file among a single reviewed path."""
    ctx, fake_adapter = _synthesis_ctx(
        [
            "[]",  # batch_1 (a.py) ok
            "no json",  # batch_2 (b.py) main call
            "still no json",  # batch_2 reformat retry -> failed
        ]
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    # 3 calls: batch_1 + batch_2 + retry. No 4th (synthesis) call.
    assert len(fake_adapter.calls) == 3


# ============================================================================
# Timeout fallback for worktree_reference batches (+ early worktree release)
# ============================================================================


class _FakeExitCodeAdapter:
    """Fake adapter scripted with (exit_code, stdout) tuples, one per call."""

    cli_name = SupportedCLI.CLAUDE
    supports_structured_output = False
    supports_tool_restriction = False
    supports_effort_control = False

    def __init__(self, script: list[tuple[int, str]]):
        self._script = list(script)
        self.calls: list[dict] = []

    def is_available(self) -> bool:
        return True

    def execute(self, prompt: str, cwd=None, timeout=None, json_schema=None, disallowed_tools=None, effort=None) -> HeadlessResponse:
        self.calls.append({"prompt": prompt, "effort": effort})
        exit_code, stdout = self._script[len(self.calls) - 1]
        return HeadlessResponse(stdout=stdout, stderr="", exit_code=exit_code)


def _timeout_ctx(adapter_script: list[tuple[int, str]], *, worktree_reference: bool = True):
    fake_adapter = _FakeExitCodeAdapter(adapter_script)
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.data["review_profile"] = ReviewProfile(findings_batch_concurrency=1)
    if worktree_reference:
        ctx.data["review_context_batches"] = [
            _make_worktree_reference_batch("batch_1", "border.py")
        ]
    else:
        ctx.data["review_context_batches"] = [_make_findings_batch("batch_1", {"border.py": 100})]
    ctx.data["review_strategy"] = ReviewStrategy(
        strategy=ReviewStrategyType.BATCHED_FINDINGS,
        size_class=PRSizeClass.SMALL,
        max_focus_files=10,
        max_prompt_chars=20000,
        max_comment_entries=5,
    )
    ctx.data["review_diff"] = (
        "diff --git a/border.py b/border.py\n"
        "index 111..222 100644\n"
        "--- a/border.py\n"
        "+++ b/border.py\n"
        "@@ -1,2 +1,3 @@\n"
        " context\n"
        "+added line\n"
        " context\n"
    )
    ctx.data["cli_preference"] = "auto"
    ctx.data["project_root"] = "/tmp/project"
    return ctx, fake_adapter


def test_ai_review_findings_retries_timed_out_worktree_batch_with_hunks(monkeypatch):
    """A timed-out worktree_reference batch reviewed NOTHING — one bounded retry with
    inline hunks turns a total loss into guaranteed coverage of the batch's files."""
    ctx, fake_adapter = _timeout_ctx(
        [
            (124, ""),  # batch_1: CLI timeout while exploring the worktree
            (0, '[{"title": "Found on retry", "path": "border.py"}]'),  # batch_1_retry
        ]
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Success)
    assert len(fake_adapter.calls) == 2
    retry_prompt = fake_adapter.calls[1]["prompt"]
    assert "added line" in retry_prompt  # inline hunks, no worktree exploration
    assert "Read from worktree" not in retry_prompt
    assert ctx.data["raw_findings"] == [{"title": "Found on retry", "path": "border.py"}]
    assert ctx.data["ai_findings_failed"] is False


def test_ai_review_findings_no_timeout_retry_for_inline_batches(monkeypatch):
    """Timeouts on batches that already had inline hunks don't retry — the fallback
    only exists for worktree_reference exploration blowups."""
    ctx, fake_adapter = _timeout_ctx([(124, "")], worktree_reference=False)
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Error)  # 0/1 batches produced output (005)
    assert len(fake_adapter.calls) == 1


def test_ai_review_findings_timeout_retry_failure_keeps_batch_failed(monkeypatch):
    ctx, fake_adapter = _timeout_ctx(
        [
            (124, ""),  # batch_1 timeout
            (1, ""),  # retry also fails
        ]
    )
    monkeypatch.setattr(code_review_steps, "_resolve_headless_adapter", lambda _pref: fake_adapter)

    result = ai_review_findings(ctx)

    assert isinstance(result, Error)  # still 0/N succeeded
    assert len(fake_adapter.calls) == 2


def test_release_review_worktree_cleans_and_clears_context(monkeypatch):
    import titan_plugin_github.operations as gh_operations

    removed = []
    monkeypatch.setattr(
        gh_operations, "cleanup_worktree", lambda git, path: removed.append(path) or True
    )

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.git = Mock()
    ctx.data["worktree_created"] = True
    ctx.data["worktree_path"] = "/tmp/wt/titan-review-9"

    code_review_steps._release_review_worktree(ctx)

    assert removed == ["/tmp/wt/titan-review-9"]
    assert ctx.data["worktree_created"] is False
    assert ctx.data["worktree_path"] is None


def test_validate_review_actions_releases_worktree_even_with_no_actions(monkeypatch):
    """The early-release must also cover the no-actions path: the user can still quit
    at the submit prompt afterwards, and the worktree must not depend on reaching the
    final cleanup step."""
    import titan_plugin_github.operations as gh_operations

    removed = []
    monkeypatch.setattr(
        gh_operations, "cleanup_worktree", lambda git, path: removed.append(path) or True
    )

    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.git = Mock()
    ctx.data["review_action_proposals"] = []
    ctx.data["worktree_created"] = True
    ctx.data["worktree_path"] = "/tmp/wt/titan-review-9"

    result = code_review_steps.validate_review_actions(ctx)

    assert isinstance(result, Skip)
    assert removed == ["/tmp/wt/titan-review-9"]


def test_validate_review_actions_uses_portable_item_review(monkeypatch):
    action = ReviewActionProposal(
        action_type=ReviewActionType.NEW_COMMENT,
        source=ReviewActionSource.NEW_FINDING,
        path="Sources/App.swift",
        line=42,
        title="Avoid the race",
        body="Protect this mutation with the actor.",
        reasoning="Two tasks can write concurrently.",
        evidence="The closure runs outside the actor.",
        severity=FindingSeverity.BLOCKING,
    )
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.interaction = Mock()
    ctx.interaction.item_review.return_value = ItemReviewResponse(
        items=[ItemReviewDecision(item_id="review-action-1", action="approve")]
    )
    ctx.data["review_action_proposals"] = [action]
    ctx.data["review_diff"] = "@@ -41,1 +42,1 @@\n+unsafeMutation()"

    monkeypatch.setattr(code_review_steps, "resolve_action_anchors", lambda actions, *_args, **_kwargs: actions)
    monkeypatch.setattr(code_review_steps, "extract_diff_hunk_for_action", lambda *_args, **_kwargs: ctx.data["review_diff"])
    monkeypatch.setattr(code_review_steps, "extract_file_excerpt_for_action", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_review_steps, "_release_review_worktree", lambda _ctx: None)

    result = code_review_steps.validate_review_actions(ctx)

    assert isinstance(result, Success)
    assert result.metadata["approved_action_proposals"] == [action]
    state = ctx.interaction.item_review.call_args.kwargs["state"]
    assert state.items[0].status == "blocking"
    assert state.items[0].editable is True
    assert [block.type for block in state.items[0].content_blocks] == [
        "markdown",
        "diff",
        "structured_summary",
    ]


def test_validate_review_actions_applies_portable_edit(monkeypatch):
    action = ReviewActionProposal(
        action_type=ReviewActionType.NEW_COMMENT,
        source=ReviewActionSource.NEW_FINDING,
        title="Improve error handling",
        body="Original comment",
        reasoning="The error is discarded.",
        severity=FindingSeverity.IMPORTANT,
    )
    ctx = WorkflowContext()
    ctx.textual = _FakeTextual()
    ctx.interaction = Mock()
    ctx.interaction.item_review.return_value = ItemReviewResponse(
        items=[
            ItemReviewDecision(
                item_id="review-action-1",
                action="edit",
                content="Edited comment",
            )
        ]
    )
    ctx.data["review_action_proposals"] = [action]

    monkeypatch.setattr(code_review_steps, "resolve_action_anchors", lambda actions, *_args, **_kwargs: actions)
    monkeypatch.setattr(code_review_steps, "extract_diff_hunk_for_action", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(code_review_steps, "extract_file_excerpt_for_action", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_review_steps, "_release_review_worktree", lambda _ctx: None)

    result = code_review_steps.validate_review_actions(ctx)

    assert isinstance(result, Success)
    assert result.metadata["approved_action_proposals"][0].body == "Edited comment"
