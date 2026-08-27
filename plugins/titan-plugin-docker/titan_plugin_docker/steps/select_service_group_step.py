# plugins/titan-plugin-docker/titan_plugin_docker/steps/select_service_group_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.ui.tui.widgets import OptionItem

from ..operations import resolve_services, list_group_names
from ..exceptions import DockerError


def select_service_group_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Let the user pick which compose services to operate on.

    Offers each group configured in `ctx.docker.service_groups`, plus an
    "All services" option. Projects with no configured groups only see
    "All services".

    Outputs (saved to ctx.data):
        docker_services (List[str]): Resolved service names (empty list means "all services")

    Returns:
        Success: A service selection was resolved
        Error: Docker client not available, or no selection was made
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    if not ctx.docker:
        return Error("Docker client not available in context")

    ctx.textual.begin_step("Select Docker Services")

    group_names = list_group_names(ctx.docker.service_groups)

    ALL_SERVICES = ""  # sentinel distinct from any real group name
    options = [OptionItem(value=ALL_SERVICES, title="All services", description="Operate on every service in the compose file")]
    options.extend(
        OptionItem(value=name, title=name, description=", ".join(ctx.docker.service_groups[name]))
        for name in group_names
    )

    selected_group = ctx.textual.ask_option("Which services?", options=options)
    if selected_group is None:
        ctx.textual.error_text("No selection was made.")
        ctx.textual.end_step("error")
        return Error("No service selection was made.")

    try:
        services = resolve_services(ctx.docker.service_groups, group=selected_group or None)
    except DockerError as e:
        ctx.textual.error_text(str(e))
        ctx.textual.end_step("error")
        return Error(str(e))

    label = selected_group or "all services"
    ctx.textual.success_text(f"Selected: {label}")
    ctx.textual.end_step("success")

    return Success(
        f"Resolved services for '{label}'",
        metadata={"docker_services": services},
    )
