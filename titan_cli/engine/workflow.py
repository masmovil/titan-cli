"""
BaseWorkflow - Orchestrator for executing atomic steps.
"""

from typing import List, Callable
from .context import WorkflowContext
from .results import WorkflowResult, Success, Error, Skip, is_error, is_skip, is_success


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
        if ctx.ui.text:
            ctx.ui.text.title(f"🚀 {self.name}")
            ctx.ui.text.line()

        final_result: WorkflowResult = Success(f"{self.name} completed")

        for i, step in enumerate(self.steps, start=1):
            step_name = step.__name__

            if ctx.ui.text:
                ctx.ui.text.info(f"[{i}/{len(self.steps)}] {step_name}")

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
                    if ctx.ui.text:
                        ctx.ui.text.line()
                        ctx.ui.text.error(f"❌ Workflow halted: {result.message}")
                    return result

            except Exception as e:
                error_msg = f"Step '{step_name}' raised exception: {e}"
                if ctx.ui.text:
                    ctx.ui.text.error(error_msg)

                final_result = Error(error_msg, exception=e)
                if self.halt_on_error:
                    return final_result

            if ctx.ui.text:
                ctx.ui.text.line()

        if is_success(final_result):
            if ctx.ui.text:
                ctx.ui.text.success(f"✅ {self.name} completed successfully")

        return final_result

    def _log_result(self, ctx: WorkflowContext, result: WorkflowResult) -> None:
        """Log step result with appropriate styling."""
        if not ctx.ui.text:
            return

        if is_success(result):
            ctx.ui.text.success(f"  ✓ {result.message}")
        elif is_skip(result):
            ctx.ui.text.warning(f"  ⊝ {result.message}")
        elif is_error(result):
            ctx.ui.text.error(f"  ✗ {result.message}")
