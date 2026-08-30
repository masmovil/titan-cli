# plugins/titan-plugin-docker/titan_plugin_docker/steps/build_push_images_step.py
from textual.widgets import Log

from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError

from ..operations import resolve_build_targets
from ..exceptions import DockerError


# Console height while a build is streaming vs. once it has finished. Finished
# logs are collapsed so a multi-target build doesn't scroll away past results.
LIVE_CONSOLE_HEIGHT = 40
FINISHED_CONSOLE_HEIGHT = 12

# The console is a `Log`, not a `TextArea`: Log is Textual's append-only
# streaming widget. TextArea is an editor — flooding it with per-line
# `insert()` calls from a worker thread (exactly what a fully-cached build
# does: a hundred lines in one burst) desyncs its wrapped-layout cache and
# the rendering degrades to one character per row, even though the document
# itself is correct. Log has no edit machinery to desync.


def _make_on_output(app, console: Log):
    def _append_line(line: str) -> None:
        # Log drops truly empty lines; buildx uses them as block separators,
        # so keep them as a single space to preserve the log's rhythm.
        console.write_line(line or " ")

    def on_output(line: str) -> None:
        if hasattr(app, "stream_output"):
            app.stream_output(line)
            return
        try:
            app.call_from_thread(_append_line, line)
        except Exception:
            pass

    return on_output


def _collapse_console(app, console: Log) -> None:
    def _apply() -> None:
        console.styles.height = FINISHED_CONSOLE_HEIGHT
        console.scroll_end(animate=False)

    try:
        app.call_from_thread(_apply)
    except Exception:
        pass


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

        console = Log(highlight=False, auto_scroll=True)
        console.styles.height = LIVE_CONSOLE_HEIGHT
        console.styles.border = ("round", "gray")
        ctx.textual.mount(console)

        result = ctx.docker.build_target(target, on_output=_make_on_output(ctx.textual.app, console))
        _collapse_console(ctx.textual.app, console)

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
