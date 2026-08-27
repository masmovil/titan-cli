# plugins/titan-plugin-docker/titan_plugin_docker/steps/disk_usage_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError


def disk_usage_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Show a host-wide Docker disk usage breakdown (images, containers, local
    volumes, build cache) as a table.

    Outputs (saved to ctx.data):
        docker_disk_usage (UIDiskUsage): The full disk usage report

    Returns:
        Success: Disk usage retrieved and displayed
        Error: Docker client not available, or the command failed
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    if not ctx.docker:
        return Error("Docker client not available in context")

    ctx.textual.begin_step("Docker Disk Usage")

    with ctx.textual.loading("Fetching disk usage..."):
        result = ctx.docker.disk_usage()

    match result:
        case ClientSuccess(data=usage):
            rows = [
                [entry.resource_type, entry.total_count, entry.active, entry.size, entry.reclaimable]
                for entry in usage.entries
            ]
            ctx.textual.table(
                headers=["Type", "Total", "Active", "Size", "Reclaimable"],
                rows=rows,
                title="docker system df",
            )
            ctx.textual.end_step("success")
            return Success("Disk usage retrieved", metadata={"docker_disk_usage": usage})
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to get disk usage: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to get disk usage: {err}")


__all__ = ["disk_usage_step"]
