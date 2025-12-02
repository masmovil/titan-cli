"""
BaseWorkflow - Orchestrator for executing atomic steps.
"""

from typing import List, Callable
from .context import WorkflowContext
from .results import WorkflowResult, Success, Error, Skip, is_error, is_skip, is_success
from ..messages import msg # Import messages


# Type alias for a step function
StepFunction = Callable[[WorkflowContext], WorkflowResult]


class BaseWorkflow:
    """
    Base workflow orchestrator.
    
    Executes a sequence of atomic steps with:
    - Sequential execution
    - Error handling (halt on Error)
    - Success/Skip/Error logging
    - Progress tracking
    
    Example:
        def step1(ctx: WorkflowContext) -> WorkflowResult:
            ctx.ui.text.info("Running step 1")
            return Success("Step 1 completed")
        
        def step2(ctx: WorkflowContext) -> WorkflowResult:
            if not ctx.has('data_from_step1'):
                return Error("Missing data from step 1")
            return Success("Step 2 completed")
        
        workflow = BaseWorkflow(
            name="My Workflow",
            steps=[step1, step2]
        )
        result = workflow.run(ctx)
    """

    def __init__(
        self,
        name: str,
        steps: List[StepFunction],
        halt_on_error: bool = True
    ):
        """
        Initialize workflow.
        
        Args:
            name: Workflow name (for logging)
            steps: List of step functions
            halt_on_error: Stop execution on first error (default: True)
        """
        self.name = name
        self.steps = steps
        self.halt_on_error = halt_on_error

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        """
        Execute workflow steps sequentially.
        
        Args:
            ctx: Workflow context with dependencies
        
        Returns:
            Final workflow result (Success or Error)
        """
        if ctx.ui and ctx.ui.text:
            # Using an emoji from a potential new EMOJI category in messages
            # Assuming "ROCKET" is a key like "🚀"
            title = msg.Workflow.TITLE.format(emoji=msg.EMOJI.ROCKET, name=self.name)
            ctx.ui.text.title(title)
            ctx.ui.text.line()

        final_result: WorkflowResult = Success(msg.Workflow.COMPLETED_SUCCESS.format(name=self.name))

        for i, step in enumerate(self.steps, start=1):
            step_name = step.__name__

            if ctx.ui and ctx.ui.text:
                step_info = msg.Workflow.STEP_INFO.format(
                    current_step=i,
                    total_steps=len(self.steps),
                    step_name=step_name
                )
                ctx.ui.text.info(step_info)

            try:
                result = step(ctx)
                final_result = result

                # Auto-merge metadata into context
                if isinstance(result, (Success, Skip)) and result.metadata:
                    ctx.data.update(result.metadata)

                # Log result
                self._log_result(ctx, result)

                # Handle errors
                if is_error(result) and self.halt_on_error:
                    if ctx.ui and ctx.ui.text:
                        ctx.ui.text.line()
                        halt_message = msg.Workflow.HALTED.format(message=result.message)
                        ctx.ui.text.error(f"{msg.EMOJI.ERROR} {halt_message}")
                    return result

            except Exception as e:
                error_msg = msg.Workflow.STEP_EXCEPTION.format(step_name=step_name, error=e)
                if ctx.ui and ctx.ui.text:
                    ctx.ui.text.error(error_msg)

                final_result = Error(error_msg, exception=e)
                if self.halt_on_error:
                    return final_result

            if ctx.ui and ctx.ui.text:
                ctx.ui.text.line()

        if is_success(final_result) and not is_skip(final_result):
            if ctx.ui and ctx.ui.text:
                success_message = msg.Workflow.COMPLETED_SUCCESS.format(name=self.name)
                ctx.ui.text.success(f"{msg.EMOJI.SUCCESS} {success_message}")
        elif is_skip(final_result):
            if ctx.ui and ctx.ui.text:
                skip_message = msg.Workflow.COMPLETED_WITH_SKIPS.format(name=self.name)
                ctx.ui.text.warning(f"{msg.SYMBOL.SKIPPED} {skip_message}")

        return final_result

    def _log_result(self, ctx: WorkflowContext, result: WorkflowResult) -> None:
        """Log step result with appropriate styling."""
        if not (ctx.ui and ctx.ui.text):
            return

        if is_success(result):
            log_msg = msg.Workflow.STEP_SUCCESS.format(symbol=msg.SYMBOL.SUCCESS, message=result.message)
            ctx.ui.text.success(log_msg)
        elif is_skip(result):
            # Assuming a new symbol for skip
            log_msg = msg.Workflow.STEP_SKIPPED.format(symbol=msg.SYMBOL.SKIPPED, message=result.message)
            ctx.ui.text.warning(log_msg)
        elif is_error(result):
            log_msg = msg.Workflow.STEP_ERROR.format(symbol=msg.SYMBOL.ERROR, message=result.message)
            ctx.ui.text.error(log_msg)
