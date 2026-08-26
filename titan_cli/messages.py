"""
Centralized Messages for Titan CLI

All user-visible text should be defined here for:
- Consistency across the application
- Easy maintenance and updates
- Future i18n support if needed
- Clear organization by feature

Usage:
    from titan_cli.messages import msg

    typer.echo(msg.CLI.VERSION.format(version="0.1.0"))
"""


class Messages:
    """All user-visible messages organized by category"""

    # ═══════════════════════════════════════════════════════════════
    # CLI Core Messages
    # ═══════════════════════════════════════════════════════════════

    class CLI:
        """Main CLI application messages"""
        APP_NAME = "titan"
        APP_DESCRIPTION = "Titan CLI - Development tools orchestrator"
        VERSION = "Titan CLI v{version}"

    # ═══════════════════════════════════════════════════════════════
    # Workflow Engine
    # ═══════════════════════════════════════════════════════════════

    class Workflow:
        """Workflow execution messages"""

        # Workflow lifecycle
        TITLE = "{emoji} {name}"
        STEP_INFO = "[{current_step}/{total_steps}] {step_name}"
        STEP_EXCEPTION = "Step '{step_name}' raised an exception: {error}"
        HALTED = "Workflow halted: {message}"
        COMPLETED_SUCCESS = "{name} completed successfully"
        COMPLETED_WITH_SKIPS = "{name} completed with skips"

        # Step result logging
        STEP_SUCCESS = "  {symbol} {message}"
        STEP_SKIPPED = "  {symbol} {message}"
        STEP_ERROR = "  {symbol} {message}"

        # Pre-flight checks
        UNCOMMITTED_CHANGES_WARNING: str = "You have uncommitted changes."
        UNCOMMITTED_CHANGES_PROMPT_TITLE: str = "Uncommitted Changes Detected"
        WORKFLOW_STEPS_INFO: str = """This workflow will:
  1. Prompt you for a commit message (or skip if you prefer)
  2. Create and push the commit
  3. Use AI to generate PR title and description automatically"""
        CONTINUE_PROMPT: str = "Continue?"

    # ═══════════════════════════════════════════════════════════════
    # AI Assistant Step
    # ═══════════════════════════════════════════════════════════════

    class AIAssistant:
        """Messages for the AI Code Assistant step."""
        UI_CONTEXT_NOT_AVAILABLE = "UI context is not available for this step."
        CONTEXT_KEY_REQUIRED = "Parameter 'context_key' is required for ai_code_assistant step"
        NO_DATA_IN_CONTEXT = "No data found in context key '{context_key}' - skipping AI assistance"
        INVALID_PROMPT_TEMPLATE = "Invalid prompt_template: missing placeholder {e}"
        FAILED_TO_BUILD_PROMPT = "Failed to build prompt: {e}"
        CONFIRM_LAUNCH_ASSISTANT = "Would you like AI assistance to help fix these issues?"
        DECLINED_ASSISTANCE_STOPPED = "User declined AI assistance - workflow stopped"
        DECLINED_ASSISTANCE_SKIPPED = "User declined AI assistance"
        NO_ASSISTANT_CLI_FOUND = "No AI coding assistant CLI found"
        AI_DISABLED = "AI is turned off for the assistant task - skipping"
        ROUTING_UNAVAILABLE = "AI routing is not available in this workflow context."
        CONFIGURE_HINT = "Set a default CLI in AI Configuration (main menu)."
        INTERACTIVE_CLI_REQUIRED = (
            "This step needs an interactive CLI session, but '{provider}' is configured for it. "
            "Choose a CLI in AI Configuration (main menu)."
        )
        LAUNCHING_ASSISTANT = "Launching {cli_name}..."
        PROMPT_PREVIEW = "Prompt: {prompt_preview}"
        BACK_IN_TITAN = "Back in Titan workflow"
        ASSISTANT_EXITED_WITH_CODE = "{cli_name} exited with code {exit_code}"

    # ═══════════════════════════════════════════════════════════════
    # Generic Error Messages
    # ═══════════════════════════════════════════════════════════════

    class Errors:
        """Generic error messages"""

        # Plugin / Core Errors
        PLUGIN_LOAD_FAILED = "Failed to load plugin '{plugin_name}': {error}"
        PLUGIN_INIT_FAILED = "Failed to initialize plugin '{plugin_name}': {error}"
        PLUGIN_INCOMPATIBLE = "Plugin '{plugin_name}' is not compatible with this Titan CLI: {detail}"
        PLUGIN_API_MISSING = (
            "uses an API that does not exist in titan-cli {current} ({error}). "
            "It was likely built for a different titan-cli version — update the plugin."
        )
        CONFIG_PARSE_ERROR = "Failed to parse configuration file at {file_path}: {error}"

        # File system
        FILE_NOT_FOUND = "File not found: {path}"
        FILE_READ_ERROR = "Cannot read file: {path}"
        FILE_WRITE_ERROR = "Cannot write file: {path}"
        DIRECTORY_NOT_FOUND = "Directory not found: {path}"
        PERMISSION_DENIED = "Permission denied: {path}"

        # Input validation
        INVALID_INPUT = "Invalid input: {value}"
        MISSING_REQUIRED = "Missing required field: {field}"
        INVALID_FORMAT = "Invalid format: {value}"

        # Network
        NETWORK_ERROR = "Network error: {error}"
        TIMEOUT = "Operation timed out"
        CONNECTION_FAILED = "Connection failed: {error}"

        # General
        UNKNOWN_ERROR = "An unknown error occurred: {error}"
        NOT_IMPLEMENTED = "Feature not implemented yet"
        OPERATION_CANCELLED = "Operation cancelled"
        OPERATION_CANCELLED_NO_CHANGES = "Operation cancelled. No changes were made."

        # Config specific
        CONFIG_WRITE_FAILED = "Failed to write configuration file: {error}"
        PROJECT_ROOT_NOT_SET = "Project root not set. Cannot discover projects."


# Singleton instance for easy access
msg = Messages()
