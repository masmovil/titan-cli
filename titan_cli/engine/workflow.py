"""
BaseWorkflow - Orchestrator for executing atomic steps.
"""

from typing import List, Callable, Optional
from .context import WorkflowContext
from .results import WorkflowResult, Success, Error, Skip


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
            ctx.text.info("Running step 1")
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
        if ctx.text:
            ctx.text.title(f"🚀 {self.name}")
            ctx.text.line()

        for i, step in enumerate(self.steps, start=1):
            step_name = step.__name__

            if ctx.text:
                ctx.text.info(f"[{i}/{len(self.steps)}] {step_name}")

            try:
                result = step(ctx)

                # Log result
                self._log_result(ctx, result)

                # Handle errors
                if result.is_error() and self.halt_on_error:
                    if ctx.text:
                        ctx.text.line()
                        ctx.text.error(f"❌ Workflow halted: {result.message}")
                    return result

            except Exception as e:
                error_msg = f"Step '{step_name}' raised exception: {e}"
                if ctx.text:
                    ctx.text.error(error_msg)

                if self.halt_on_error:
                    return Error(error_msg)

            if ctx.text:
                ctx.text.line()

        # All steps completed
        if ctx.text:
            ctx.text.success(f"✅ {self.name} completed successfully")

        return Success(f"{self.name} completed")

    def _log_result(self, ctx: WorkflowContext, result: WorkflowResult) -> None:
        """Log step result with appropriate styling."""
        if not ctx.text:
            return

        if result.is_success() and not result.is_skip():
            ctx.text.success(f"  ✓ {result.message}")
        elif result.is_skip():
            ctx.text.warning(f"  ⊝ {result.message}")
        elif result.is_error():
            ctx.text.error(f"  ✗ {result.message}")
