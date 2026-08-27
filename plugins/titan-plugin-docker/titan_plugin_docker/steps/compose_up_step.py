# plugins/titan-plugin-docker/titan_plugin_docker/steps/compose_up_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError


def compose_up_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Start compose services.

    Inputs (from ctx.data):
        docker_services (List[str], optional): Service names to start (empty/absent starts all services)

    Returns:
        Success: Services started
        Error: Docker client not available, or the compose command failed
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    if not ctx.docker:
        return Error("Docker client not available in context")

    ctx.textual.begin_step("Start Docker Services")

    services = ctx.get("docker_services", [])
    label = ", ".join(services) if services else "all services"

    with ctx.textual.loading(f"Starting {label}..."):
        result = ctx.docker.compose_up(services=services)

    match result:
        case ClientSuccess():
            ctx.textual.success_text(f"Started: {label}")
            ctx.textual.end_step("success")
            return Success(f"Started {label}", metadata={"docker_services": services})
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to start services: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to start services: {err}")


__all__ = ["compose_up_step"]
