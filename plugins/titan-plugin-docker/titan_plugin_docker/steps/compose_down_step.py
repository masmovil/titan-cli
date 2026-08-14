# plugins/titan-plugin-docker/titan_plugin_docker/steps/compose_down_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError


def compose_down_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Stop compose services.

    Inputs (from ctx.data):
        docker_services (List[str], optional): Service names to stop (empty/absent stops the whole project)

    Returns:
        Success: Services stopped
        Error: Docker client not available, or the compose command failed
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    if not ctx.docker:
        return Error("Docker client not available in context")

    ctx.textual.begin_step("Stop Docker Services")

    services = ctx.get("docker_services", [])
    label = ", ".join(services) if services else "the project"

    with ctx.textual.loading(f"Stopping {label}..."):
        result = ctx.docker.compose_down(services=services)

    match result:
        case ClientSuccess():
            ctx.textual.success_text(f"Stopped: {label}")
            ctx.textual.end_step("success")
            return Success(f"Stopped {label}", metadata={"docker_services": services})
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to stop services: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to stop services: {err}")


__all__ = ["compose_down_step"]
