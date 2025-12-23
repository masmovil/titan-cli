from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator

class WorkflowStepModel(BaseModel):
    """
    Represents a single step in a workflow.
    """
    id: Optional[str] = Field(None, description="Unique identifier for the step. Auto-generated from name if not provided.")
    name: Optional[str] = Field(None, description="Human-readable name for the step.")
    plugin: Optional[str] = Field(None, description="The plugin providing the step (e.g., 'git', 'github').")
    step: Optional[str] = Field(None, description="The name of the step function within the plugin.")
    command: Optional[str] = Field(None, description="A shell command to execute.")
    workflow: Optional[str] = Field(None, description="The name of another workflow to execute.")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters to pass to the step or command.")
    on_error: Literal["fail", "continue"] = Field("fail", description="Action to take if the step fails.")
    use_shell: bool = Field(False, description="If true, execute the command in a shell. WARNING: This can be a security risk if the command uses untrusted input.")

    # Used only in base workflow definitions to mark injection points for hooks
    hook: Optional[str] = Field(None, description="Marks this step as a hook point for extension.")

    @model_validator(mode='after')
    def validate_step_type(self):
        """
        Validate that the step has exactly one of: (plugin + step), command, or workflow.
        Also auto-generates id from name if not provided.
        """
        # Auto-generate id from name if not provided
        if not self.id:
            if self.name:
                # Convert name to valid id: lowercase, replace non-alphanumeric with underscore
                import re
                self.id = re.sub(r'[^a-z0-9_]', '_', self.name.lower()).strip('_')
            elif self.hook:
                # For hook-only steps, use hook name as id
                self.id = f"hook_{self.hook}"
            elif self.plugin and self.step:
                # For plugin steps, use plugin_step as id
                self.id = f"{self.plugin}_{self.step}"
            elif self.workflow:
                # For workflow steps, use workflow name as id
                self.id = f"workflow_{self.workflow.replace(':', '_').replace('/', '_')}"
            elif self.command:
                # For command steps, generate generic id
                self.id = "command_step"
            else:
                # Fallback
                self.id = "step"

        # A step can be just a hook, in which case other fields are not needed.
        if self.hook:
            return self

        has_plugin_step = self.plugin is not None and self.step is not None
        has_command = self.command is not None
        has_workflow = self.workflow is not None

        provided_actions = sum([has_plugin_step, has_command, has_workflow])

        if provided_actions > 1:
            raise ValueError(f"Step '{self.id}' can only have one action type, but found multiple: "
                             f"{'plugin/step, ' if has_plugin_step else ''}"
                             f"{'command, ' if has_command else ''}"
                             f"{'workflow' if has_workflow else ''}".strip(', '))

        if provided_actions == 0 and not self.hook:
            raise ValueError(f"Step '{self.id}' must define an action: either (plugin and step), a command, a workflow, or a hook.")

        return self


class WorkflowConfigModel(BaseModel):
    """
    Represents the overall configuration of a workflow.
    """
    name: str = Field(..., description="The name of the workflow.")
    description: Optional[str] = Field(None, description="A description of what the workflow does.")
    source: Optional[str] = Field(None, description="Where the workflow is defined (e.g., 'plugin:github').")
    extends: Optional[str] = Field(None, description="The base workflow this workflow extends.")
    
    params: Dict[str, Any] = Field(default_factory=dict, description="Workflow-level parameters that can be overridden.")
    
    # For base workflows: list of hook names (e.g., ["before_commit"])
    # For extending workflows: dict of hook_name -> list of steps to inject
    # This will be handled during loading/merging by the WorkflowLoader,
    # so we define it broadly here and refine during processing.
    hooks: Optional[Union[List[str], Dict[str, List[WorkflowStepModel]]]] = Field(None, description="Hook definitions or steps to inject into hooks.")
    
    steps: List[WorkflowStepModel] = Field(default_factory=list, description="The sequence of steps in the workflow.")
