# plugins/titan-plugin-docker/titan_plugin_docker/steps/select_services_to_stop_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Exit
from titan_cli.core.result import ClientSuccess, ClientError
from titan_cli.ui.tui.widgets import SelectionOption

from ..operations import resolve_stop_selection


def select_services_to_stop_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Let the user pick which running services to stop, via a checkbox list
    where every service starts checked.

    Unchecking a service keeps it running; if every service is left checked,
    the whole project is torn down (`docker compose down`) instead of
    stopping each service individually.

    Outputs (saved to ctx.data):
        docker_services (List[str]): Resolved service names (empty list means "down the whole project")

    Returns:
        Success: A stop selection was resolved
        Error: Docker client not available, listing services failed, or no selection was made
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    if not ctx.docker:
        return Error("Docker client not available in context")

    ctx.textual.begin_step("Select Services to Stop")

    result = ctx.docker.list_services()

    match result:
        case ClientSuccess(data=all_services):
            pass
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to list services: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to list services: {err}")

    if not all_services:
        ctx.textual.error_text("No services found in the compose file.")
        ctx.textual.end_step("error")
        return Error("No services found in the compose file.")

    options = [SelectionOption(value=name, label=name, selected=True) for name in all_services]
    selected = ctx.textual.ask_multiselect("Which services should be stopped?", options)

    if not selected:
        # Nothing left checked means "stop nothing" - distinct from the
        # empty list `ComposeService.down` treats as "stop everything",
        # so this must short-circuit before reaching that step.
        ctx.textual.dim_text("No services selected - nothing to stop.")
        ctx.textual.end_step("skip")
        return Exit("No services selected to stop", metadata={"docker_services": []})

    services = resolve_stop_selection(all_services, selected)

    label = "the whole project" if not services else ", ".join(services)
    ctx.textual.success_text(f"Will stop: {label}")
    ctx.textual.end_step("success")

    return Success(
        f"Resolved services to stop: {label}",
        metadata={"docker_services": services},
    )


__all__ = ["select_services_to_stop_step"]
