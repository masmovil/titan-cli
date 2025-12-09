"""
Platform Agent as Workflow Step

Wrappers to use PlatformAgent as workflow steps in analysis mode.

This module provides convenience functions to integrate PlatformAgent
with the workflow system, allowing the same agent configuration (TOML)
to be used both interactively (with TAP tools) and as analysis steps.
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Skip, Success, Error
from titan_cli.agents.platform_agent import PlatformAgent
from typing import Optional


def platform_agent_analysis_step(
    ctx: WorkflowContext,
    agent_config: str = "config/agents/platform_agent.toml",
    task: Optional[str] = None
) -> WorkflowResult:
    """
    Run PlatformAgent in analysis mode as a workflow step.

    This step loads PlatformAgent from TOML config and runs it in
    analysis mode, which analyzes data from ctx.data without executing tools.

    Args:
        ctx: Workflow context (with ai, data from previous steps)
        agent_config: Path to agent TOML configuration
        task: Optional task description (overrides TOML prompt)

    Reads from ctx.data:
        - git_status (from get_git_status_step)
        - git_diff (if available)
        - commit_message, pr_info, etc.

    Writes to ctx.data:
        - agent_analysis: The analysis text from AI

    Returns:
        Success: With analysis in metadata["agent_analysis"]
        Skip: If AI not configured or no data
        Error: If agent loading or execution fails

    Example:
        workflow = BaseWorkflow(steps=[
            get_git_status_step,           # Populates ctx.data
            platform_agent_analysis_step   # Analyzes with PlatformAgent
        ])

        result = workflow.run(ctx)
        analysis = result.metadata.get("agent_analysis")
    """

    # Check AI availability
    if not ctx.ai:
        return Skip("AI not configured, skipping Platform Agent analysis")

    try:
        # Load PlatformAgent from TOML
        agent = PlatformAgent.from_toml(agent_config)

        # Get task from context, parameter, or use empty
        user_context = ctx.data.get("agent_task") or task or ""

        # Run agent in analysis mode
        result = agent.run(
            ctx=ctx,
            user_context=user_context,
            mode="analysis"
        )

        # If successful, add analysis to metadata with standard key
        if isinstance(result, Success):
            return Success(
                result.message,
                metadata={
                    **result.metadata,
                    "agent_analysis": result.message  # Standard key
                }
            )
        else:
            return result

    except FileNotFoundError:
        return Error(f"Agent config not found: {agent_config}")
    except Exception as e:
        return Error(f"Platform Agent execution failed: {e}", exception=e)


def platform_agent_suggest_commit_step(
    ctx: WorkflowContext,
    agent_config: str = "config/agents/platform_agent.toml"
) -> WorkflowResult:
    """
    Use PlatformAgent to suggest a conventional commit message.

    This is a specialized wrapper that:
    1. Runs PlatformAgent in analysis mode
    2. Asks specifically for a commit message
    3. Extracts the message from the response
    4. Sets ctx.data["commit_message"] for use by create_git_commit_step

    Args:
        ctx: Workflow context
        agent_config: Path to agent TOML config

    Reads from ctx.data:
        - git_status (required)
        - git_diff (optional, improves accuracy)

    Writes to ctx.data:
        - suggested_commit_message: AI-generated message
        - commit_message: Same as above (for create_git_commit_step)

    Returns:
        Success: With commit message in metadata
        Skip: If AI not configured or working directory clean
        Error: If generation fails

    Example:
        workflow = BaseWorkflow(steps=[
            get_git_status_step,
            platform_agent_suggest_commit_step,  # ← Generates commit message
            create_git_commit_step               # ← Uses the message
        ])
    """

    # Check AI
    if not ctx.ai:
        return Skip("AI not configured, skipping commit suggestion")

    # Check if there's anything to commit
    git_status = ctx.data.get("git_status")
    if git_status and git_status.is_clean:
        return Skip("Working directory is clean, no commit needed")

    if not git_status and not ctx.data.get("git_diff"):
        return Skip("No git data to analyze for commit message")

    try:
        # Load PlatformAgent
        agent = PlatformAgent.from_toml(agent_config)

        # Run analysis with commit-specific task
        result = agent.run(
            ctx=ctx,
            user_context=(
                "Generate a single conventional commit message for these changes. "
                "Format: type(scope): description. "
                "Return ONLY the commit message, no explanation."
            ),
            mode="analysis"
        )

        if isinstance(result, Success):
            # Clean up the message (remove markdown, extra whitespace, etc.)
            commit_msg = result.message.strip()

            # Remove common markdown artifacts
            commit_msg = commit_msg.strip('`').strip()

            # Remove "commit:" prefix if AI added it
            if commit_msg.lower().startswith('commit:'):
                commit_msg = commit_msg[7:].strip()

            # Take first line if multi-line
            if '\n' in commit_msg:
                commit_msg = commit_msg.split('\n')[0].strip()

            return Success(
                f"Suggested: {commit_msg}",
                metadata={
                    "suggested_commit_message": commit_msg,
                    "commit_message": commit_msg  # Auto-populate for next step
                }
            )
        else:
            return result

    except FileNotFoundError:
        return Error(f"Agent config not found: {agent_config}")
    except Exception as e:
        return Error(f"Failed to suggest commit message: {e}", exception=e)


def create_platform_agent_step(
    agent_config: str,
    task: str
):
    """
    Factory function to create a custom PlatformAgent step.

    This allows creating specialized steps with specific configurations
    and tasks while reusing the same underlying agent.

    Args:
        agent_config: Path to agent TOML config
        task: Task description for the agent

    Returns:
        A workflow step function

    Example:
        # Create custom step
        review_security_step = create_platform_agent_step(
            agent_config="config/agents/security_agent.toml",
            task="Review for security vulnerabilities"
        )

        # Use in workflow
        workflow = BaseWorkflow(steps=[
            get_git_diff_step,
            review_security_step
        ])
    """
    def step(ctx: WorkflowContext) -> WorkflowResult:
        return platform_agent_analysis_step(ctx, agent_config, task)

    # Set descriptive name
    agent_name = agent_config.split('/')[-1].replace('.toml', '')
    step.__name__ = f"platform_agent_{agent_name}_step"

    return step
