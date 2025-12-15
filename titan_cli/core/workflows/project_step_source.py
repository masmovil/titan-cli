import importlib.util
from pathlib import Path
from typing import Callable, Dict, Any, Optional, List
from dataclasses import dataclass

from titan_cli.engine.context import WorkflowContext
from titan_cli.engine.results import WorkflowResult

# Define a type alias for a Step Function
StepFunction = Callable[[WorkflowContext, Dict[str, Any]], WorkflowResult]

@dataclass
class StepInfo:
    """
    Metadata for a discovered project step.
    """
    name: str
    path: Path
    
class ProjectStepSource:
    """
    Discovers and loads Python step functions from a project's .titan/steps/ directory.
    """
    def __init__(self, project_root: Path):
        self._project_root = project_root
        self._steps_dir = self._project_root / ".titan" / "steps"
        self._step_info_cache: Optional[List[StepInfo]] = None
        self._step_function_cache: Dict[str, StepFunction] = {}

    def discover(self) -> List[StepInfo]:
        """
        Discovers all available step files in the project's .titan/steps directory.
        """
        if self._step_info_cache is not None:
            return self._step_info_cache

        if not self._steps_dir.is_dir():
            self._step_info_cache = []
            return []

        discovered = []
        for step_file in self._steps_dir.glob("*.py"):
            if not step_file.name.startswith("__"):
                step_name = step_file.stem
                discovered.append(StepInfo(name=step_name, path=step_file))
        
        self._step_info_cache = discovered
        return discovered

    def get_step(self, step_name: str) -> Optional[StepFunction]:
        """
        Retrieves a step function by name, loading it from its file if necessary.
        """
        if step_name in self._step_function_cache:
            return self._step_function_cache[step_name]

        # Find the step info from the discovered list
        discovered_steps = self.discover()
        step_info = next((s for s in discovered_steps if s.name == step_name), None)

        if not step_info:
            return None

        try:
            spec = importlib.util.spec_from_file_location(step_name, step_info.path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Convention: the step function has the same name as the file
                step_func = getattr(module, step_name, None)
                if callable(step_func):
                    self._step_function_cache[step_name] = step_func
                    return step_func
                else:
                    # Optional: Log a warning if a file exists but the function doesn't
                    pass
                    
        except Exception as e:
            # Optional: Log a more detailed error
            print(f"Error loading project step '{step_name}': {e}")

        return None

