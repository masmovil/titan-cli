# plugins/titan-plugin-docker/titan_plugin_docker/steps/select_containers_to_remove_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Exit
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.ui.tui.widgets import SelectionOption

from ..operations import list_removable_containers


def select_containers_to_remove_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    List every container on the host (not just this project's), and let the
    user pick which stopped ones to remove via a checkbox list where nothing
    starts checked - this is host-wide and destructive, so each container
    requires an explicit opt-in.

    Running containers are shown for context but are not offered for removal.

    Outputs (saved to ctx.data):
        docker_container_ids (List[str]): Container IDs selected for removal

    Returns:
        Success: A removal selection was made
        Error: Docker client not available, or listing containers failed
        Exit: No stopped containers exist, or nothing was selected
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    if not ctx.docker:
        return Error("Docker client not available in context")

    ctx.textual.begin_step("Select Containers to Remove")

    result = ctx.docker.list_containers()

    match result:
        case ClientSuccess(data=all_containers):
            pass
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to list containers: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to list containers: {err}")

    rows = [[c.state_icon, c.name, c.image, c.status] for c in all_containers]
    ctx.textual.table(headers=["", "Name", "Image", "Status"], rows=rows, title="All containers on this host")

    removable = list_removable_containers(all_containers)
    if not removable:
        ctx.textual.dim_text("No stopped containers to remove.")
        ctx.textual.end_step("skip")
        return Exit("No stopped containers to remove", metadata={"docker_container_ids": []})

    options = [
        SelectionOption(
            value=container.container_id,
            label=f"{container.name} ({container.image}) - {container.status}",
            selected=False,
        )
        for container in removable
    ]
    selected = ctx.textual.ask_multiselect("Which stopped containers should be removed?", options)

    if not selected:
        ctx.textual.dim_text("No containers selected - nothing to remove.")
        ctx.textual.end_step("skip")
        return Exit("No containers selected to remove", metadata={"docker_container_ids": []})

    ctx.textual.success_text(f"Will remove {len(selected)} container(s)")
    ctx.textual.end_step("success")

    return Success(
        f"Selected {len(selected)} container(s) for removal",
        metadata={"docker_container_ids": selected},
    )


__all__ = ["select_containers_to_remove_step"]
