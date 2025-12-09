"""
AI-powered atomic commits generation step.

Analyzes staged and unstaged changes to create atomic commits automatically.
"""

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip


def ai_create_atomic_commits(ctx: WorkflowContext, **kwargs) -> WorkflowResult:
    """
    Analyze changes and create atomic commits automatically using AI.

    This step:
    1. Analyzes all modified files
    2. Groups changes by logical units (features, fixes, refactors)
    3. Creates atomic commits for each group
    4. Uses conventional commits format

    Reads from ctx.data:
        - git_status: Current git status with changes
        - use_ai: Must be true (this step requires AI)

    Writes to ctx.data:
        - commits_created: List of commit messages created
        - total_commits: Number of commits created

    Returns:
        Success: Commits created successfully
        Skip: No changes, AI not configured, or user declined
        Error: Failed to create commits
    """
    # Check if AI is configured
    if not ctx.ai:
        return Skip("AI not configured. Run 'titan ai configure' to enable AI features.")

    # Get git status
    git_status = ctx.data.get("git_status")
    if not git_status or git_status.is_clean:
        return Skip("No changes to commit")

    # Get git client
    git_client = ctx.git
    if not git_client:
        return Error("Git client not available")

    try:
        # Get all modified and untracked files
        all_files = git_status.modified_files + git_status.untracked_files

        if not all_files:
            return Skip("No files to commit")

        # Show files to user
        if ctx.ui:
            ctx.ui.text.info(f"📝 Analyzing {len(all_files)} changed files...")
            ctx.ui.spacer.small()

        # Get diff for each file
        file_diffs = {}
        for file_path in all_files:
            try:
                diff = git_client.get_file_diff(file_path)
                file_diffs[file_path] = diff
            except Exception as e:
                if ctx.ui:
                    ctx.ui.text.warning(f"Could not get diff for {file_path}: {e}")

        if not file_diffs:
            return Skip("No diffs available for analysis")

        # Build AI prompt for atomic commits analysis
        files_summary = "\n".join([f"  - {f}" for f in file_diffs.keys()])

        # Get detailed diffs (limited to avoid token limits)
        diffs_text = ""
        for file_path, diff in list(file_diffs.items())[:10]:  # Limit to first 10 files
            diffs_text += f"\n### {file_path}\n```diff\n{diff[:1000]}\n```\n"

        if len(file_diffs) > 10:
            diffs_text += f"\n... and {len(file_diffs) - 10} more files\n"

        prompt = f"""Analyze these changes and propose atomic commits.

## Changed Files ({len(file_diffs)} total)
{files_summary}

## Sample Diffs
{diffs_text}

## Instructions
Create atomic commits that group related changes. Each commit should:
1. Focus on a single logical change (feature, fix, refactor, docs, etc.)
2. Use conventional commits format: type(scope): description
3. Be descriptive but concise (max 72 chars for title)

Format your response EXACTLY like this:

COMMIT 1:
FILES: file1.py, file2.py
MESSAGE: feat(auth): add user authentication system

COMMIT 2:
FILES: test_auth.py
MESSAGE: test(auth): add authentication tests

COMMIT 3:
FILES: README.md
MESSAGE: docs: update README with auth setup

Propose between 1-5 atomic commits based on the changes.
"""

        if ctx.ui:
            ctx.ui.text.info("🤖 AI is analyzing changes to create atomic commits...")
            ctx.ui.spacer.small()

        # Call AI
        from titan_cli.agents import PlatformAgent

        try:
            agent = PlatformAgent.from_toml("config/agents/platform_agent.toml")
        except FileNotFoundError:
            return Skip(
                "PlatformAgent config not found at config/agents/platform_agent.toml. "
                "Cannot create atomic commits without AI agent configuration."
            )

        result = agent.run(
            ctx=ctx,
            user_context=prompt,
            mode="analysis"
        )

        if not isinstance(result, Success):
            return result

        # Parse AI response
        response = result.message

        if "COMMIT" not in response:
            return Error(
                f"AI response format incorrect. Expected 'COMMIT N:' sections.\n"
                f"Got: {response[:200]}..."
            )

        # Parse commits from response
        commits = []
        current_commit = None

        for line in response.split("\n"):
            line = line.strip()

            if line.startswith("COMMIT"):
                if current_commit and current_commit.get("message"):
                    commits.append(current_commit)
                current_commit = {"files": [], "message": ""}

            elif line.startswith("FILES:") and current_commit is not None:
                files_str = line.replace("FILES:", "").strip()
                current_commit["files"] = [f.strip() for f in files_str.split(",")]

            elif line.startswith("MESSAGE:") and current_commit is not None:
                current_commit["message"] = line.replace("MESSAGE:", "").strip()

        # Add last commit
        if current_commit and current_commit.get("message"):
            commits.append(current_commit)

        if not commits:
            return Error("AI did not propose any commits")

        # Show proposed commits to user
        if ctx.ui:
            ctx.ui.spacer.small()
            ctx.ui.text.subtitle(f"📦 AI Proposed {len(commits)} Atomic Commits:")
            ctx.ui.spacer.small()

            for i, commit in enumerate(commits, 1):
                files_list = ", ".join(commit["files"][:3])
                if len(commit["files"]) > 3:
                    files_list += f" (+{len(commit['files']) - 3} more)"

                ctx.ui.text.body(f"  {i}. {commit['message']}", style="bold cyan")
                ctx.ui.text.body(f"     Files: {files_list}", style="dim")

            ctx.ui.spacer.small()

            # Ask user confirmation
            proceed = ctx.views.prompts.ask_confirm(
                "Create these atomic commits?",
                default=True
            )

            if not proceed:
                return Skip("User declined to create atomic commits")

        # Create commits
        created_commits = []

        for i, commit in enumerate(commits, 1):
            try:
                if ctx.ui:
                    ctx.ui.text.info(f"Creating commit {i}/{len(commits)}: {commit['message']}")

                # Stage files for this commit
                for file_path in commit["files"]:
                    if file_path in all_files:
                        git_client.stage_file(file_path)

                # Create commit
                commit_result = git_client.commit(commit["message"])

                if commit_result:
                    created_commits.append(commit["message"])
                    if ctx.ui:
                        ctx.ui.text.success(f"  ✓ Created: {commit['message']}")

            except Exception as e:
                if ctx.ui:
                    ctx.ui.text.warning(f"  ✗ Failed to create commit: {e}")

        if not created_commits:
            return Error("No commits were created")

        if ctx.ui:
            ctx.ui.spacer.small()
            ctx.ui.text.success(f"✅ Successfully created {len(created_commits)} atomic commits")

        # Save to context
        return Success(
            f"Created {len(created_commits)} atomic commits",
            metadata={
                "commits_created": created_commits,
                "total_commits": len(created_commits)
            }
        )

    except Exception as e:
        if ctx.ui:
            ctx.ui.text.warning(f"Atomic commits failed: {e}")
            ctx.ui.text.info("Falling back to single commit...")

        return Skip(f"Atomic commits failed: {e}")


# Export for plugin registration
__all__ = ["ai_create_atomic_commits"]
