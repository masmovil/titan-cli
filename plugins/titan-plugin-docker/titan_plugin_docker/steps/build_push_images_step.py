# plugins/titan-plugin-docker/titan_plugin_docker/steps/build_push_images_step.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError

from ..operations import resolve_build_targets
from ..exceptions import DockerError


def _make_on_output(ctx: WorkflowContext):
    """Forward Docker output through the portable interaction contract."""

    def on_output(line: str) -> None:
        ctx.interaction.stream_output(line or " ")

    return on_output


def build_push_images_step(ctx: WorkflowContext) -> WorkflowResult:
    """
    Build (and push, per target config) one or all configured Docker images.

    Each target gets its own bordered container in the execution panel, titled
    with the image name and platforms, so it is obvious where one build ends and
    the next begins. Inside it, `docker buildx build` output streams into a live,
    selectable/copyable text area (collapsed once the build finishes) instead of
    a plain spinner, so progress is visible for long builds and the log can be
    copied out.

    Inputs (from ctx.data):
        build_target_name (str, optional): Name of a single configured build target
            (absent builds every target configured for the project)

    Outputs (saved to ctx.data):
        docker_build_results (List[UIBuildResult]): One result per built image

    Returns:
        Success: All requested targets built
        Error: Docker client not available, no targets configured/matched, or a build failed
    """
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    if not ctx.docker:
        return Error("Docker client not available in context")

    target_name = ctx.get("build_target_name")

    try:
        targets = resolve_build_targets(ctx.docker.build_targets, name=target_name)
    except DockerError as e:
        ctx.textual.begin_step("Build Docker Images")
        ctx.textual.error_text(str(e))
        ctx.textual.end_step("error")
        return Error(str(e))

    if not targets:
        ctx.textual.begin_step("Build Docker Images")
        ctx.textual.error_text("No build targets configured for this project.")
        ctx.textual.end_step("error")
        return Error("No build targets configured for this project.")

    results = []
    for index, target in enumerate(targets, start=1):
        platforms = target.platforms or "builder native"
        ctx.textual.begin_step(f"[{index}/{len(targets)}] {target.name} ({platforms})")

        result = ctx.docker.build_target(target, on_output=_make_on_output(ctx))

        match result:
            case ClientSuccess(data=build_result):
                ctx.textual.success_text(build_result.summary)
                ctx.textual.end_step("success")
                results.append(build_result)
            case ClientError(error_message=err):
                ctx.textual.error_text(f"Failed to build {target.name}: {err}")
                ctx.textual.end_step("error")
                return Error(f"Failed to build {target.name}: {err}")

    ctx.textual.begin_step("Build Summary")
    for build_result in results:
        ctx.textual.success_text(build_result.summary)
    ctx.textual.end_step("success")

    return Success(
        f"Built {len(results)} image(s)",
        metadata={"docker_build_results": results},
    )


__all__ = ["build_push_images_step"]
