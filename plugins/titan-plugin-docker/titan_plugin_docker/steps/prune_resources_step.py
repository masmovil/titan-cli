# plugins/titan-plugin-docker/titan_plugin_docker/steps/prune_resources_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError


def prune_resources_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Prune the resource categories selected in `prune_targets`.

    Inputs (from ctx.data):
        prune_targets (List[str]): Target keys to prune (see `PruneService.PRUNE_COMMANDS`)

    Outputs (saved to ctx.data):
        docker_prune_results (List[UIPruneEntry]): One result per pruned target

    Returns:
        Success: Selected targets pruned
        Error: Docker client not available, no targets selected, or a prune command failed
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    if not ctx.docker:
        return Error("Docker client not available in context")

    ctx.textual.begin_step("Prune Docker Resources")

    targets = ctx.get("prune_targets", [])
    if not targets:
        ctx.textual.error_text("No prune targets selected.")
        ctx.textual.end_step("error")
        return Error("No prune targets selected.")

    with ctx.textual.loading(f"Pruning {', '.join(targets)}..."):
        result = ctx.docker.prune(targets)

    match result:
        case ClientSuccess(data=results):
            rows = [[entry.target, entry.reclaimed] for entry in results]
            ctx.textual.table(headers=["Target", "Reclaimed"], rows=rows, title="Prune results")
            ctx.textual.end_step("success")
            return Success(
                f"Pruned {len(results)} target(s)",
                metadata={"docker_prune_results": results},
            )
        case ClientError(error_message=err):
            ctx.textual.error_text(f"Failed to prune: {err}")
            ctx.textual.end_step("error")
            return Error(f"Failed to prune: {err}")


__all__ = ["prune_resources_step"]
