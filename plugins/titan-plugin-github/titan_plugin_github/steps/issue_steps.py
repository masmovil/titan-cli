import ast
from titan_cli.ai.router.declaration import declare_ai_usage
from titan_cli.ai.router.enums import AIProviderType, AITask
from titan_cli.ai.router.models import AIExecutionError, AIExecutionSuccess
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import WorkflowResult, Success, Error, Skip
from titan_cli.core.result import ClientSuccess, ClientError
from ..agents.issue_generator import IssueGeneratorAgent
from ..operations import filter_valid_labels
from pathlib import Path

@declare_ai_usage(
    task=AITask.ISSUE_GENERATION,
    # The agent drives whatever generator it is handed, so either transport
    # works. Remote leads because a CLI costs a subprocess per agent call.
    executes=[AIProviderType.REMOTE, AIProviderType.CLI_HEADLESS],
    preferred=[AIProviderType.REMOTE],
    enforces=True,
)
def ai_suggest_issue_title_and_body_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Use AI to suggest a title and description for a GitHub issue.
    Auto-categorizes and selects the appropriate template.

    Inputs (from ctx.data):
        issue_body (str): Raw issue request entered by the user.

    Outputs (saved to ctx.data):
        issue_title (str): AI-generated or user-edited title.
        issue_body (str): AI-generated or user-edited body.
        issue_category (str): Detected issue category.
        labels (list[str]): Suggested labels for the issue.

    Returns:
        Success: If issue content is generated and accepted.
        Skip: If AI is unavailable or the user rejects the generated issue.
        Error: If required context is missing or generation fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step container
    ctx.textual.begin_step("Categorize and Generate Issue")

    # Use whatever the user chose for this task; the agent drives it either way.
    generator = ctx.ai
    if ctx.ai_router:
        match ctx.ai_router.resolve_generator(
            policy=ai_suggest_issue_title_and_body_step,
            cwd=ctx.git.repo_path if ctx.git else None,
            announce=ctx.textual.ai_chip,
        ):
            case AIExecutionSuccess(data=resolved):
                generator = resolved
            case AIExecutionError(error_code="AI_DISABLED", error_message=disabled_message):
                ctx.textual.dim_text(disabled_message)
                ctx.textual.end_step("skip")
                return Skip(disabled_message)
            case AIExecutionError(error_message=err):
                ctx.textual.error_text(err)
                ctx.textual.end_step("error")
                return Error(err)

    if not generator or not generator.is_available():
        ctx.textual.dim_text("AI client not available")
        ctx.textual.end_step("skip")
        return Skip("AI client not available")

    issue_body_prompt = ctx.get("issue_body")
    if not issue_body_prompt:
        ctx.textual.error_text("issue_body not found in context")
        ctx.textual.end_step("error")
        return Error("issue_body not found in context")

    ctx.textual.dim_text("Using AI to categorize and generate issue...")
    try:
        # Get available labels from repository for smart mapping
        available_labels = None
        if ctx.github:
            result = ctx.github.list_labels()
            match result:
                case ClientSuccess(data=labels):
                    available_labels = labels
                case ClientError():
                    # If we can't get labels, continue without filtering
                    pass

        # Get template directory from repo path
        template_dir = None
        if ctx.git:
            template_dir = Path(ctx.git.repo_path) / ".github" / "ISSUE_TEMPLATE"

        issue_generator = IssueGeneratorAgent(generator, template_dir=template_dir)

        with ctx.textual.loading("Generating issue with AI..."):
            result = issue_generator.generate_issue(issue_body_prompt, available_labels=available_labels)

        # Show category detected
        category = result["category"]
        template_used = result.get("template_used", False)

        ctx.textual.text("")  # spacing
        ctx.textual.success_text(f"Category detected: {category}")

        if template_used:
            ctx.textual.success_text(f"Using template: {category}.md")
        else:
            ctx.textual.warning_text(f"No template found for {category}, using default structure")

        # Use the reusable AI content review flow
        review = ctx.interaction.review_generated_content(
            interaction_id="review-generated-issue",
            content_title=result["title"],
            content_body=result["body"],
            header_text="AI-Generated Issue",
            title_label="Title:",
            description_label="Description:",
            choice_question="What would you like to do with this issue?",
        )

        # Handle rejection
        if review.action == "reject":
            ctx.textual.warning_text("User rejected AI-generated issue")
            ctx.textual.end_step("skip")
            return Skip("User rejected AI-generated issue")

        # Save the final content (whether used as-is or edited)
        ctx.set("issue_title", review.title)
        ctx.set("issue_body", review.content)
        ctx.set("issue_category", category)
        ctx.set("labels", result["labels"])

        ctx.textual.end_step("success")
        return Success(f"AI-generated issue ({category}) ready")
    except Exception as e:
        ctx.textual.error_text(f"Failed to generate issue: {e}")
        ctx.textual.end_step("error")
        return Error(f"Failed to generate issue: {e}")


def create_issue_steps(ctx: WorkflowContext) -> WorkflowResult:
    """
    Create a new GitHub issue.

    Requires:
        ctx.github: An initialized GitHubClient.

    Inputs (from ctx.data):
        issue_title (str): Issue title.
        issue_body (str): Issue body.
        assignees (list, optional): Usernames to assign.
        labels (list, optional): Labels to apply.

    Outputs (saved to ctx.data):
        issue (GitHubIssue): The created issue object.

    Returns:
        Success: If the issue is created successfully.
        Error: If required context is missing or the GitHub call fails.
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Begin step container
    ctx.textual.begin_step("Create Issue")

    if not ctx.github:
        ctx.textual.error_text("GitHub client not available")
        ctx.textual.end_step("error")
        return Error("GitHub client not available")

    issue_title = ctx.get("issue_title")
    issue_body = ctx.get("issue_body")
    assignees = ctx.get("assignees", [])
    labels = ctx.get("labels", [])

    # Safely parse string representations to lists
    if isinstance(assignees, str):
        try:
            assignees = ast.literal_eval(assignees)
        except (ValueError, SyntaxError):
            assignees = []

    if isinstance(labels, str):
        try:
            labels = ast.literal_eval(labels)
        except (ValueError, SyntaxError):
            labels = []

    # Ensure they are lists
    if not isinstance(assignees, list):
        assignees = []
    if not isinstance(labels, list):
        labels = []

    if not issue_title:
        ctx.textual.error_text("issue_title not found in context")
        ctx.textual.end_step("error")
        return Error("issue_title not found in context")

    if not issue_body:
        ctx.textual.error_text("issue_body not found in context")
        ctx.textual.end_step("error")
        return Error("issue_body not found in context")

    # Filter labels to only those that exist in the repository
    if labels and ctx.github:
        result = ctx.github.list_labels()
        match result:
            case ClientSuccess(data=available_labels):
                valid_labels, invalid_labels = filter_valid_labels(labels, available_labels)
                if invalid_labels:
                    ctx.textual.warning_text(f"Skipping invalid labels: {', '.join(invalid_labels)}")
                labels = valid_labels
            case ClientError():
                # If we can't validate labels, continue with all labels anyway
                pass

    ctx.textual.dim_text(f"Creating issue: {issue_title}...")
    result = ctx.github.create_issue(
        title=issue_title,
        body=issue_body,
        assignees=assignees,
        labels=labels,
    )

    match result:
        case ClientSuccess(data=issue):
            ctx.textual.text("")  # spacing
            ctx.textual.success_text(f"Successfully created issue #{issue.number}")
            ctx.textual.end_step("success")
            return Success(
                f"Successfully created issue #{issue.number}",
                metadata={"issue": issue}
            )
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to create issue: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to create issue: {err}")
