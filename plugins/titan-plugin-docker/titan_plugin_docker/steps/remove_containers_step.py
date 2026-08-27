# plugins/titan-plugin-docker/titan_plugin_docker/steps/remove_containers_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError


def remove_containers_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Remove the containers selected in `docker_container_ids`.

    Inputs (from ctx.data):
        docker_container_ids (List[str]): Container IDs to remove

    Returns:
        Success: Containers removed
        Error: Docker client not available, no containers selected, or removal failed
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    if not ctx.docker:
        return Error("Docker client not available in context")

    ctx.textual.begin_step("Remove Containers")

    container_ids = ctx.get("docker_container_ids", [])
    if not container_ids:
        ctx.textual.error_text("No containers selected for removal.")
        ctx.textual.end_step("error")
        return Error("No containers selected for removal.")

    with ctx.textual.loading(f"Removing {len(container_ids)} container(s)..."):
        result = ctx.docker.remove_containers(container_ids)

    match result:
        case ClientSuccess(data=removed):
            ctx.textual.success_text(f"Removed {len(removed)} container(s)")
            ctx.textual.end_step("success")
            return Success(f"Removed {len(removed)} container(s)", metadata={"docker_container_ids": removed})
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to remove containers: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to remove containers: {err}")


__all__ = ["remove_containers_step"]
