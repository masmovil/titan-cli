"""
Centralized Messages for Titan CLI

All user-visible text should be defined here for:
- Consistency across the application
- Easy maintenance and updates
- Future i18n support if needed
- Clear organization by feature

Usage:
    from titan_cli.messages import msg

    ctx.ui.panel.print(msg.GitHub.PR_CREATED.format(number=123))
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

        # Interactive menu (future)
        MENU_TITLE = "Titan CLI - Main Menu"
        MENU_SELECT_OPTION = "Select an option:"
        MENU_EXIT = "Exit"

    class Interactive:
        """Interactive Mode Messages"""
        MAIN_MENU_TITLE = "What would you like to do?"
        SELECT_PROJECT_TITLE = "Select a project to initialize"
        RETURN_TO_MENU_PROMPT = "Press Enter to return to the main menu"
        RETURN_TO_MENU_PROMPT_CONFIRM = "Return to the main menu?"
        GOODBYE = "Goodbye!"
        INIT_PROJECT_TITLE = "Initializing Titan Project: [primary]{project_name}[/primary]"

    # ═══════════════════════════════════════════════════════════════
    # Projects
    # ═══════════════════════════════════════════════════════════════
    class Projects:
        """Project related messages"""
        LIST_TITLE = "List Configured Projects"
        CONFIGURE_TITLE = "Configure a New Project"
        INIT_SUCCESS = "Project '{project_name}' initialized successfully at: {config_path}"
        INIT_CANCELLED = "Project initialization cancelled."
        SECRET_SAVED = "{key} saved securely ({scope} scope)"
        ACTIVE_PROJECT_SET = "Active project set to: {project_name}"

    # ═══════════════════════════════════════════════════════════════
    # UI Components
    # ═══════════════════════════════════════════════════════════════
    class UI:
        """UI component messages"""

        # Banner subtitles
        BANNER_DEFAULT = "Development Tools Orchestrator"
        BANNER_WORKFLOW = "Workflow Engine"
        BANNER_PLUGINS = "Plugin Manager"
        BANNER_GITHUB = "GitHub Integration"
        BANNER_GIT = "Git Automation"
        BANNER_JIRA = "Jira Integration"

        # Status messages
        LOADING = "Loading..."
        PROCESSING = "Processing..."
        DONE = "Done"
        CANCELLED = "Cancelled by user"

        # Generic UI messages
        PRESS_ENTER = "Press Enter to continue..."
        INVALID_CHOICE = "Invalid choice. Please try again."
    
    class EMOJI:
        """Centralized emoji characters for consistent UI"""
        SUCCESS = "✅"
        ERROR = "❌"
        INFO = "ℹ️"
        WARNING = "⚠️"
        ROCKET = "🚀"

    class SYMBOL:
        """ASCII symbols for consistent alignment (alternative to emojis)"""
        SUCCESS = "✓"  # Checkmark
        ERROR = "✗"    # Cross
        INFO = "i"     # Info
        WARNING = "!"  # Exclamation
        SKIPPED = "⊝" # Circled minus

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
    # Jira Integration
    # ═══════════════════════════════════════════════════════════════

    class Jira:
        """Jira operations messages"""

        # Issues
        ISSUE_CREATING = "Creating Jira issue..."
        ISSUE_CREATED = "Issue created: {key}"
        ISSUE_UPDATED = "Issue updated: {key}"
        ISSUE_FAILED = "Failed to create issue: {error}"
        ISSUE_NOT_FOUND = "Issue not found: {key}"

        # Transitions
        TRANSITION_EXECUTING = "Transitioning issue to: {status}"
        TRANSITION_SUCCESS = "Issue transitioned to: {status}"
        TRANSITION_FAILED = "Failed to transition issue: {error}"

        # Authentication
        AUTH_MISSING = "Jira credentials not found"
        AUTH_INVALID = "Invalid Jira credentials"

    # ═══════════════════════════════════════════════════════════════
    # AI Integration
    # ═══════════════════════════════════════════════════════════════

    class AI:
        """AI operations messages"""

        # General
        PROCESSING = "AI processing..."
        COMPLETED = "AI processing completed"
        FAILED = "AI processing failed: {error}"

        # Reviews
        REVIEW_GENERATING = "Generating AI review..."
        REVIEW_GENERATED = "AI review generated"

        # Code generation
        CODE_GENERATING = "Generating code..."
        CODE_GENERATED = "Code generated"

        # Configuration
        CONFIG_TITLE = "Configure AI Provider"
        PROVIDER_SELECT_TITLE = "Select AI Provider"
        PROVIDER_SELECT_CATEGORY = "Providers"
        PROVIDER_NOT_CONFIGURED = "No AI provider configured. Run: titan ai configure"
        PROVIDER_INVALID = "Invalid AI provider: {provider}"
        API_KEY_MISSING = "API key not found for provider: {provider}"
        API_KEY_PROMPT = "Enter your {provider} API Key"
        API_KEY_ALREADY_CONFIGURED = "API key already configured for {provider}."
        API_KEY_REPLACE_PROMPT = "Do you want to replace the existing key?"
        GEMINI_OAUTH_PROMPT = "Use OAuth for Gemini authentication?"
        GEMINI_OAUTH_INFO = "Gemini can use OAuth via Google Cloud SDK."
        GEMINI_OAUTH_NOT_AVAILABLE = "Google Cloud SDK not found or not working: {error}"
        GEMINI_OAUTH_NOT_AUTHENTICATED = "You are not authenticated with gcloud."
        GEMINI_OAUTH_RUN_LOGIN_PROMPT = "Run 'gcloud auth application-default login' now?"
        GEMINI_OAUTH_CONFIGURED_SUCCESS = "Successfully configured Gemini to use OAuth."

        CUSTOM_ENDPOINT_PROMPT = "Do you use a custom API endpoint? (e.g., corporate proxy, AWS Bedrock)"
        CUSTOM_ENDPOINT_INFO_TITLE = "Custom endpoints are used for:"
        CUSTOM_ENDPOINT_INFO_PROXY = "  • Corporate/enterprise proxies"
        CUSTOM_ENDPOINT_INFO_BEDROCK = "  • AWS Bedrock"

        CUSTOM_ENDPOINT_INFO_SELF_HOSTED = "  • Self-hosted deployments"
        CUSTOM_ENDPOINT_EXAMPLE_ANTHROPIC = "Example: https://bedrock-runtime.us-east-1.amazonaws.com"

        CUSTOM_ENDPOINT_URL_PROMPT = "Enter custom API endpoint URL"
        CUSTOM_ENDPOINT_SUCCESS = "Will use custom endpoint: {base_url}"
        CUSTOM_ENDPOINT_USING_STANDARD = "Using standard endpoint"

        CONFIG_SUCCESS_TITLE = "AI provider configured:"
        CONFIG_SUCCESS_PROVIDER = "  Provider: {provider}"
        CONFIG_SUCCESS_MODEL = "  Model: {model}"
        CONFIG_SUCCESS_ENDPOINT = "  Endpoint: {base_url}"
        CONFIG_SUCCESS_TEMPERATURE = "  Temperature: {temperature}"
        CONFIG_SUCCESS_MAX_TOKENS = "  Max Tokens: {max_tokens}"

        RECONFIGURE_PROMPT = "Reconfigure now?"

        # Advanced Options
        ADVANCED_OPTIONS_PROMPT = "Set advanced options (temperature, max_tokens)?"
        TEMPERATURE_PROMPT = "Enter default temperature (0.0 to 2.0, affects creativity)"
        MAX_TOKENS_PROMPT = "Enter default max tokens (e.g., 4096, max output length)"
        

        # Model Selection
        MODEL_SELECTION_TITLE = "Model Selection for {provider}"
        MODEL_SELECTION_TIP = "Tip: You can enter any model name, including custom/enterprise models"
        MODEL_PROMPT = "Enter model name (or press Enter for default)"
        
        # Popular Models - Anthropic
        POPULAR_CLAUDE_MODELS_TITLE = "Popular Claude models:"
        POPULAR_CLAUDE_SONNET_3_5 = "  • claude-3-5-sonnet-20241022 - Latest, balanced performance"
        POPULAR_CLAUDE_OPUS = "  • claude-3-opus-20240229 - Most capable, best for complex tasks"
        POPULAR_CLAUDE_HAIKU = "  • claude-3-haiku-20240307 - Fastest, cost-effective"
        POPULAR_CLAUDE_HAIKU_3_5 = "  • claude-3-5-haiku-20241022 - New fast model"



        # Popular Models - Gemini
        POPULAR_GEMINI_MODELS_TITLE = "Popular Gemini models:"
        POPULAR_GEMINI_1_5_PRO = "  • gemini-1.5-pro - Latest pro model"
        POPULAR_GEMINI_1_5_FLASH = "  • gemini-1.5-flash - Fast and efficient"
        POPULAR_GEMINI_PRO = "  • gemini-pro - Standard model"

        # Connection Test
        TESTING_CONNECTION = "Testing {provider} connection{model_info}{endpoint_info}..."
        TEST_CONNECTION_PROMPT = "Test AI connection now?"
        TEST_MODEL_INFO = "Model: {model}"
        TEST_RESPONSE_INFO = "Response: {content}"
        CONNECTION_SUCCESS = "Connection successful!"
        CONNECTION_FAILED = "Connection failed: {error}"
        CONNECTION_TEST_FAILED_PROMPT = "Connection test failed. You may want to reconfigure."
        MODEL_NOT_AVAILABLE = "Model not available: {model}"
        RATE_LIMIT = "Rate limit reached. Please try again later."
        
        # New AI Configuration Messages
        AI_CONFIG_PROVIDER_TITLE = "Configure AI Provider"
        AI_CONFIG_TYPE_TITLE = "Configuration Type"
        AI_CONFIG_TYPE_SELECT = "Select the type"
        AI_CONFIG_TYPE_CORPORATE_LABEL = "Corporate"
        AI_CONFIG_TYPE_CORPORATE_DESCRIPTION = "Internal endpoint (same base_url for all providers)"
        AI_CONFIG_TYPE_INDIVIDUAL_LABEL = "Individual"
        AI_CONFIG_TYPE_INDIVIDUAL_DESCRIPTION = "Personal API key (official endpoint)"
        AI_CONFIG_CANCELLED = "Configuration cancelled"
        AI_CONFIG_CORPORATE_INFO = "Corporate Configuration"
        AI_CONFIG_CORPORATE_BASE_URL_INFO = "All providers will use the same corporate base_url"
        AI_CONFIG_CORPORATE_BASE_URL_EXAMPLE = "Example: https://api.your-company.com/llm"

        AI_CONFIG_CORPORATE_BASE_URL_PROMPT = "Corporate Base URL:"

        AI_PROVIDER_SELECT_TITLE = "Select Provider"
        AI_PROVIDER_SELECT_CATEGORY = "Available Providers"
        AI_ANTHROPIC_LABEL = "Anthropic (Claude)"
        AI_ANTHROPIC_DESCRIPTION = "claude-3-5-sonnet, opus, etc."

        AI_GEMINI_LABEL = "Google Gemini"
        AI_GEMINI_DESCRIPTION = "gemini-1.5-pro, gemini-flash, etc."

        AI_API_KEY_INFO = "Configure API Key for {provider_name}"
        AI_API_KEY_PROMPT = "API Key for {provider_name}:"

        AI_PROVIDER_NAME_PROMPT = "Name for this provider:"
        AI_PROVIDER_MARK_DEFAULT_PROMPT = "Mark as default provider?"
        PROVIDER_ID_EXISTS = "Provider ID '{provider_id}' already exists. Please choose a different name."

        AI_PROVIDER_CONFIGURED_SUCCESS = "Provider configured successfully"
        AI_PROVIDER_NAME = "Name: {name}"
        AI_PROVIDER_ID = "ID: {id}"
        AI_PROVIDER_TYPE = "Type: {type}"
        AI_PROVIDER_NAME_MODEL = "Provider: {provider_name} ({model})"
        AI_PROVIDER_ENDPOINT = "Endpoint: {base_url}"

        AI_PROVIDER_NOT_FOUND_FOR_GENERATION = "AI provider '{provider_id}' not found for generation."
        AI_NO_AI_CONFIG_FOUND_TO_TEST = "No AI configuration found to test provider '{provider_id}'."
        AI_DETAILS = "Details: {error}"

        AI_NO_DEFAULT_PROVIDER = "No default AI provider configured. Please specify a provider ID to test."
        AI_TESTING_DEFAULT_PROVIDER = "Testing default AI provider: '{provider_id}'"
        AI_PROVIDER_NOT_FOUND_IN_CONFIG = "AI provider '{provider_id}' not found in configuration."
        AI_SEE_AVAILABLE_PROVIDERS = "Run 'titan ai configure' or 'titan ai list' to see available providers."


    class Code:
        """Claude Code CLI integration messages"""
        HELP_TEXT = "Launch Claude Code CLI from anywhere in Titan."
        NOT_INSTALLED = "Claude Code not installed"
        INSTALL_INSTRUCTIONS = "Install: npm install -g @anthropic/claude-code"
        LAUNCHING = "🤖 Launching Claude Code..."
        INITIAL_PROMPT = "Initial prompt: {prompt}"
        INTERRUPTED = "\nClaude Code interrupted"
        RETURNED = "✓ Back in Titan CLI"

    # ═══════════════════════════════════════════════════════════════
    # Secrets Management
    # ═══════════════════════════════════════════════════════════════
    
    class Secrets:
        """Secrets management messages"""
        AI_SETUP_CANCELLED = "AI provider setup cancelled. No changes were made."
        KEYRING_FALLBACK = "Failed to store secret in system keyring: {e}. Falling back to project scope."

    # ═══════════════════════════════════════════════════════════════
    # Plugin System
    # ═══════════════════════════════════════════════════════════════

    class Plugin:
        """Plugin system messages"""

        # Discovery
        DISCOVERING = "Discovering plugins..."
        DISCOVERED = "Discovered {count} plugin(s)"
        LOADING = "Loading plugin: {name}"
        LOADED = "Plugin loaded: {name}"
        LOAD_FAILED = "Failed to load plugin: {name} - {error}"

        # Listing
        LIST_TITLE = "Available Plugins"
        LIST_EMPTY = "No plugins found"
        LIST_ITEM = "  • {name} - {description}"

        # Errors
        NOT_FOUND = "Plugin not found: {name}"
        INVALID_PLUGIN = "Invalid plugin: {name}"
        DEPENDENCY_MISSING = "Missing dependency for plugin {name}: {dependency}"
        
        # Git Plugin specific messages
        git_client_init_warning = "GitPlugin could not initialize: {e}"
        git_client_not_available = "Git client not available. Is Git installed and in your PATH?"

    class Plugins:
        """Plugins command messages"""
        INSTALLED_TITLE = "Installed Plugins"
        TABLE_HEADER_PLUGIN = "Plugin"
        TABLE_HEADER_VERSION = "Version"
        TABLE_HEADER_STATUS = "Status"
        LOAD_FAILURE_SUMMARY = "{count} plugin(s) failed to load or initialize:"
        LOAD_FAILURE_DETAIL = "Plugin: [bold]{plugin_name}[/bold]\nError: {error_message}"
        LOAD_FAILURE_PANEL_TITLE = "{plugin_name} Failed"

        DOCTOR_TITLE = "Plugin Health Check"
        DOCTOR_CHECKING = "Checking {plugin_name}..."
        DOCTOR_UNAVAILABLE = "Plugin '[bold]{plugin_name}[/bold]' is not available.\nThis may be due to missing system dependencies or an issue during initialization."
        DOCTOR_UNAVAILABLE_TITLE = "{plugin_name} Issue"
        DOCTOR_HEALTHY = "  {plugin_name} is healthy"
        DOCTOR_LOAD_FAILURE_SUMMARY = "{count} plugin(s) failed to load:"
        DOCTOR_LOAD_FAILURE_DETAIL = "Error: {error_message}\n\n[bold]Suggestions:[/bold]\n  - Check if the plugin is correctly installed.\n  - Check for missing system dependencies."
        DOCTOR_LOAD_FAILURE_PANEL_TITLE = "{plugin_name} Failed to Load"
        DOCTOR_ALL_HEALTHY = "All plugins are healthy!"
        DOCTOR_ISSUES_FOUND = "Some plugins have issues. See details above."
        STATUS_AVAILABLE = "Available"
        STATUS_UNAVAILABLE = "Not available"
        TABLE_HEADER_ENABLED = "Enabled"
        TABLE_HEADER_CONFIGURATION = "Configuration"
        NO_CONFIG = "No config"
        PLUGIN_NOT_FOUND = "Plugin '{name}' not found"
        PLUGIN_INFO_TITLE = "Plugin: {name}"
        PLUGIN_INFO_VERSION = "Version: {version}"
        PLUGIN_INFO_DESCRIPTION = "Description: {description}"
        PLUGIN_INFO_AVAILABLE = "Available: {status}"
        PLUGIN_INFO_DEPENDENCIES = "Dependencies: {dependencies}"
        PLUGIN_INFO_SCHEMA_TITLE = "\nConfiguration Schema:"
        PLUGIN_INFO_SCHEMA_PROPERTY = "  • {prop_name}: {description}"
        PLUGIN_INFO_SCHEMA_DEFAULT = "    Default: {default}"
        PLUGIN_INFO_STEPS_TITLE = "\nAvailable Steps: {count}"
        PLUGIN_INFO_STEP = "  • {step_name}"
        CONFIGURE_TITLE = "Configuring {name}..."
        CONFIGURE_SOON = "Feature coming soon!"




    # ═══════════════════════════════════════════════════════════════
    # Configuration
    # ═══════════════════════════════════════════════════════════════

    class Config:
        """Configuration messages"""

        # Loading
        LOADING = "Loading configuration..."
        LOADED = "Configuration loaded"
        LOAD_FAILED = "Failed to load configuration: {error}"

        # File operations
        FILE_NOT_FOUND = "Configuration file not found: {path}"
        FILE_INVALID = "Invalid configuration file: {error}"
        FILE_CREATED = "Configuration file created: {path}"

        # Validation
        VALIDATING = "Validating configuration..."
        VALID = "Configuration is valid"
        INVALID = "Invalid configuration: {error}"

        # Settings
        SETTING_UPDATED = "Setting updated: {key} = {value}"
        SETTING_INVALID = "Invalid setting: {key}"
        PROJECT_ROOT_SETUP_CANCELLED = "Project root setup cancelled. Titan CLI may not function fully."

        # Saving
        SAVE_GLOBAL_CONFIG_ERROR = "Error saving global config: {e}"
        TOMLI_W_NOT_INSTALLED = "Warning: tomli_w is not installed. Cannot save global config."
        SAVE_GLOBAL_CONFIG_FAILED_UNSET = "Failed to save global config after unsetting invalid project: {e}"
        ACTIVE_PROJECT_INVALID = "Active project '{project_name}' was invalid or not configured. It has been unset. Use 'Switch Project' to select a valid project."

        # Project Root Setup
        PROJECT_ROOT_WELCOME_TITLE = "Welcome to Titan CLI! Let's get you set up."
        PROJECT_ROOT_INFO_MSG = "To get started, Titan needs to know where you store your projects."
        PROJECT_ROOT_BODY_MSG = "This is the main folder where you keep all your git repositories (e.g., ~/git, ~/Projects)."
        PROJECT_ROOT_PROMPT_MSG = "Enter the absolute path to your projects root directory"
        PROJECT_ROOT_SUCCESS_MSG = "Configuration saved. Project root set to: {project_root}"

    # ═══════════════════════════════════════════════════════════════
    # User Prompts
    # ═══════════════════════════════════════════════════════════════

    class Prompts:
        """User input prompts"""

        # General
        INVALID_INPUT = "Invalid input, please try again."
        NOT_A_NUMBER = "Please enter a number."
        VALUE_TOO_LOW = "Value must be at least {min}."
        VALUE_TOO_HIGH = "Value must be at most {max}."
        MISSING_VALUE = "A value is required."
        INVALID_MENU_CHOICE = "Please enter a number between 1 and {total_items}."

        # Confirmations
        CONFIRM_DELETE = "Are you sure you want to delete '{item}'?"
        CONFIRM_OVERWRITE = "'{path}' already exists. Overwrite?"
        CONFIRM_CONTINUE = "Continue?"
        CONFIRM_ABORT = "Abort operation?"

        # Input requests
        ENTER_NAME = "Enter a name for the project"
        ENTER_TITLE = "Enter title:"
        ENTER_DESCRIPTION = "Enter description:"
        ENTER_BRANCH = "Enter branch name:"
        ENTER_MESSAGE = "Enter message:"
        SELECT_PROJECT_TYPE = "Select a project type"
        ENTER_CUSTOM_PROJECT_TYPE = "Enter custom project type"

        # Selections
        SELECT_OPTION = "Select an option:"
        SELECT_WORKFLOW = "Select a workflow:"
        SELECT_BRANCH = "Select a branch:"
        SELECT_FILE = "Select a file:"

    # ═══════════════════════════════════════════════════════════════
    # Generic Error Messages
    # ═══════════════════════════════════════════════════════════════

    class Errors:
        """Generic error messages"""

        # Plugin / Core Errors
        PLUGIN_LOAD_FAILED = "Failed to load plugin '{plugin_name}': {error}"
        PLUGIN_INIT_FAILED = "Failed to initialize plugin '{plugin_name}': {error}"
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
