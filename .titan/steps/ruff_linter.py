import json
import subprocess
from pathlib import Path
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import Success, Error, WorkflowResult


def ruff_linter(ctx: WorkflowContext) -> WorkflowResult:
    """
    Run ruff with autofix and show diff between before/after.
    """
    if not ctx.ui:
        return Error("UI context is not available for this step.")

    project_root = ctx.get("project_root", ".") # Fallback to current dir

    # 1. Scan before fix
    ctx.ui.text.body("Running initial ruff scan...", style="dim")
    result_before = subprocess.run(
        ["poetry", "run", "ruff", "check", ".", "--output-format=json"],
        capture_output=True,
        text=True,
        cwd=project_root
    )

    try:
        errors_before = json.loads(result_before.stdout) if result_before.stdout else []
    except json.JSONDecodeError:
        return Error(f"Failed to parse initial ruff output as JSON.\n{result_before.stdout}")


    # 2. Auto-fix
    ctx.ui.text.body("Applying auto-fixes...", style="dim")
    subprocess.run(
        ["poetry", "run", "ruff", "check", ".", "--fix", "--quiet"],
        capture_output=True,
        cwd=project_root
    )

    # 3. Scan after fix
    ctx.ui.text.body("Running final ruff scan...", style="dim")
    result_after = subprocess.run(
        ["poetry", "run", "ruff", "check", ".", "--output-format=json"],
        capture_output=True,
        text=True,
        cwd=project_root
    )
    try:
        errors_after = json.loads(result_after.stdout) if result_after.stdout else []
    except json.JSONDecodeError:
        return Error(f"Failed to parse final ruff output as JSON.\n{result_after.stdout}")

    # 4. Show summary
    ctx.ui.spacer.small()
    fixed_count = len(errors_before) - len(errors_after)

    if fixed_count > 0:
        ctx.ui.text.success(f"Auto-fixed {fixed_count} issue(s)")

    if not errors_after:
        ctx.ui.text.success("All linting issues resolved!")
        return Success("Linting passed")

    # 5. Show remaining errors
    if errors_after:
        ctx.ui.text.warning(f"{len(errors_after)} issue(s) require manual fix:")
        ctx.ui.spacer.small()

        # Prepare data for the table
        table_headers = ["File", "Line", "Col", "Code", "Message"]
        table_rows = []

        for error in errors_after:
            file_path = error.get("filename", "Unknown file")
            # Make path relative to project_root if possible for cleaner display
            if project_root != "." and file_path.startswith(project_root):
                file_path = str(Path(file_path).relative_to(project_root))

            location = error.get("location", {})
            row = str(location.get("row", "?"))
            col = str(location.get("column", "?"))
            code = error.get("code", "")
            message = error.get("message", "")

            table_rows.append([file_path, row, col, code, message])

        if ctx.ui.table: # Ensure table renderer is available
            ctx.ui.table.print_table(
                headers=table_headers,
                rows=table_rows,
                show_lines=True,
                title="Remaining Ruff Issues"
            )
        else: # Fallback if table renderer is somehow not available
            for row_data in table_rows:
                ctx.ui.text.error(f"{row_data[0]}:{row_data[1]}:{row_data[2]} - [{row_data[3]}] {row_data[4]}")

        # Build formatted error list for AI assistant
        errors_text = f"{len(errors_after)} linting issues found:\n\n"
        for error in errors_after:
            file_path = error.get("filename", "Unknown file")
            if project_root != "." and file_path.startswith(project_root):
                file_path = str(Path(file_path).relative_to(project_root))

            location = error.get("location", {})
            errors_text += f"• {file_path}:{location.get('row', '?')}:{location.get('column', '?')} - [{error.get('code', '')}] {error.get('message', '')}\n"
            if error.get("url"):
                errors_text += f"  Docs: {error['url']}\n"

        # Return Success with errors in metadata for next step to consume
        return Success(
            message=f"Linting complete: {fixed_count} auto-fixed, {len(errors_after)} need manual attention",
            metadata={"step_output": errors_text}
        )

    # All issues resolved
    return Success("Linting passed - all issues resolved!")
