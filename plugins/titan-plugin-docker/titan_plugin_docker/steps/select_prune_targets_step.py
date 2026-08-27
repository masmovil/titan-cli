# plugins/titan-plugin-docker/titan_plugin_docker/steps/select_prune_targets_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Exit
from titan_cli.ui.tui.widgets import SelectionOption

_PRUNE_OPTIONS = [
    ("containers", "Stopped containers", "Remove containers that are not running"),
    ("images", "Dangling images", "Remove unreferenced (dangling) images - never removes tagged images"),
    ("build_cache", "Build cache", "Remove the buildx/BuildKit build cache"),
    ("volumes", "Unused volumes", "Remove volumes not attached to any container (Docker refuses to remove in-use volumes)"),
]


def select_prune_targets_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Let the user pick which resource categories to prune, via a checkbox
    list where nothing starts checked - pruning is destructive, so each
    category requires an explicit opt-in.

    Outputs (saved to ctx.data):
        prune_targets (List[str]): Selected target keys (see `PruneService.PRUNE_COMMANDS`)

    Returns:
        Success: A prune selection was made
        Error: Docker client not available
        Exit: Nothing was selected (nothing to prune)
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    if not ctx.docker:
        return Error("Docker client not available in context")

    ctx.textual.begin_step("Select What to Prune")

    options = [
        SelectionOption(value=key, label=f"{label} - {description}", selected=False)
        for key, label, description in _PRUNE_OPTIONS
    ]
    selected = ctx.textual.ask_multiselect("Which resource categories should be pruned?", options)

    if not selected:
        ctx.textual.dim_text("Nothing selected - nothing to prune.")
        ctx.textual.end_step("skip")
        return Exit("Nothing selected to prune", metadata={"prune_targets": []})

    ctx.textual.success_text(f"Will prune: {', '.join(selected)}")
    ctx.textual.end_step("success")

    return Success(
        f"Selected prune targets: {', '.join(selected)}",
        metadata={"prune_targets": selected},
    )


__all__ = ["select_prune_targets_step"]
