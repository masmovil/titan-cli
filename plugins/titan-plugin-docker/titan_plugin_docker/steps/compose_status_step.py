# plugins/titan-plugin-docker/titan_plugin_docker/steps/compose_status_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError


def compose_status_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Show compose project status as a table.

    Inputs (from ctx.data):
        docker_services (List[str], optional): Service names to inspect (empty/absent inspects all services)

    Outputs (saved to ctx.data):
        docker_compose_status (UIComposeStatus): The full compose status

    Returns:
        Success: Status retrieved and displayed
        Error: Docker client not available, or the compose command failed
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    if not ctx.docker:
        return Error("Docker client not available in context")

    ctx.textual.begin_step("Docker Compose Status")

    services = ctx.get("docker_services", [])

    with ctx.textual.loading("Fetching compose status..."):
        result = ctx.docker.compose_status(services=services)

    match result:
        case ClientSuccess(data=status):
            rows = [
                [service.service, service.state, service.status, service.health]
                for service in status.services
            ]
            ctx.textual.table(
                headers=["Service", "State", "Status", "Health"],
                rows=rows,
                title=status.summary,
            )
            ctx.textual.end_step("success")
            return Success(status.summary, metadata={"docker_compose_status": status})
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to get compose status: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to get compose status: {err}")


__all__ = ["compose_status_step"]
