import subprocess
import json
import os
from pathlib import Path
from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import Success, Error, WorkflowResult


def test_runner(ctx: WorkflowContext) -> WorkflowResult:
    """
    Run pytest using the --json-report flag and parse the structured output.
    """
    if not ctx.ui:
        return Error("UI context is not available for this step.")

    project_root = ctx.get("project_root", ".")
    report_path = Path(project_root) / ".report.json"

    ctx.ui.text.body("Running tests with pytest...", style="dim")

    # Run pytest with JSON report enabled
    result = subprocess.run(
        ["poetry", "run", "pytest", "--json-report", f"--json-report-file={report_path}"],
        capture_output=True,
        text=True,
        cwd=project_root
    )
    
    # Read the report
    if not report_path.exists():
        return Error(f"Pytest JSON report not found at {report_path}. Pytest output:\n{result.stderr}")

    try:
        with open(report_path) as f:
            report = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return Error(f"Failed to read or parse pytest JSON report: {e}")
    finally:
        # Clean up the report file
        if os.path.exists(report_path):
            os.remove(report_path)

    ctx.ui.spacer.small()

    # --- Extract Summary ---
    summary = report.get("summary", {})
    passed_count = summary.get("passed", 0)
    failed_count = summary.get("failed", 0)
    total_count = summary.get("total", passed_count + failed_count)
    duration = f"{report.get('duration', 0):.2f}s"

    # --- Show Summary Table ---
    if ctx.ui.table and total_count > 0:
        ctx.ui.table.print_table(
            headers=["Metric", "Value"],
            rows=[
                ["Total Tests", str(total_count)],
                ["Passed", f"✓ {passed_count}"],
                ["Failed", f"✗ {failed_count}"],
                ["Duration", duration]
            ],
            title="Test Results Summary"
        )
        ctx.ui.spacer.small()

    # --- Handle Failures ---
    if failed_count == 0:
        ctx.ui.text.success("✓ All tests passed!")
        return Success("All tests passed")

    ctx.ui.text.warning(f"{failed_count} test(s) failed")
    ctx.ui.spacer.small()

    failures = [test for test in report.get("tests", []) if test.get("outcome") == "failed"]
    
    # --- Show Failures Table ---
    if failures and ctx.ui.table:
        failure_rows = []
        for failure in failures:
            test_name = failure.get("nodeid", "Unknown Test")
            call = failure.get("call", {})
            error_repr = call.get("longrepr", "No error details")

            # Clean up test name and error message
            if len(test_name) > 60:
                test_name = "..." + test_name[-57:]
            if len(error_repr) > 150:
                error_repr = error_repr[:147] + "..."
            
            failure_rows.append([test_name, error_repr])
        
        ctx.ui.table.print_table(
            headers=["Test", "Error"],
            rows=failure_rows,
            title="Failed Tests Details",
            show_lines=True
        )
        ctx.ui.spacer.small()

    # --- Format Failures for AI ---
    failures_text = f"{failed_count} test(s) failed:\n\n"
    for failure in failures:
        failures_text += f"Test: {failure.get('nodeid', 'Unknown Test')}\n"
        failures_text += f"Error:\n  {failure.get('call', {}).get('longrepr', 'N/A')}\n\n"

    return Success(
        message="Tests completed with failures",
        metadata={"step_output": failures_text}
    )

