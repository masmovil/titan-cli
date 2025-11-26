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
        LOADING = "⏳ Loading..."
        PROCESSING = "⚙️  Processing..."
        DONE = "✅ Done"
        CANCELLED = "🚫 Cancelled by user"

        # Generic UI messages
        PRESS_ENTER = "Press Enter to continue..."
        INVALID_CHOICE = "❌ Invalid choice. Please try again."
    
    class EMOJI:
        """Centralized emoji characters for consistent UI"""
        SUCCESS = "✅"
        ERROR = "❌"
        INFO = "ℹ️"
        WARNING = "⚠️"

    class SYMBOL:
        """ASCII symbols for consistent alignment (alternative to emojis)"""
        SUCCESS = "✓"  # Checkmark
        ERROR = "✗"    # Cross
        INFO = "i"     # Info
        WARNING = "!"  # Exclamation

    # ═══════════════════════════════════════════════════════════════
    # Workflow Engine
    # ═══════════════════════════════════════════════════════════════

    class Workflow:
        """Workflow execution messages"""

        # Workflow lifecycle
        STARTING = "▶️  Starting workflow: {name}"
        EXECUTING = "⚙️  Executing workflow: {name}"
        COMPLETED = "✅ Workflow completed successfully"
        FAILED = "❌ Workflow failed: {error}"

        # Step execution
        STEP_STARTING = "   ▶️  {step}"
        STEP_COMPLETED = "   ✅ {step}"
        STEP_FAILED = "   ❌ {step}: {error}"
        STEP_SKIPPED = "   ⏭️  Skipped: {step}"

        # Workflow listing
        LIST_TITLE = "Available Workflows"
        LIST_EMPTY = "No workflows found"
        LIST_LOADED = "Loaded {count} workflow(s)"

        # Workflow errors
        NOT_FOUND = "❌ Workflow not found: {name}"
        INVALID_CONFIG = "❌ Invalid workflow configuration: {error}"
        EXECUTION_ERROR = "❌ Error executing workflow: {error}"

    # ═══════════════════════════════════════════════════════════════
    # GitHub Integration
    # ═══════════════════════════════════════════════════════════════

    class GitHub:
        """GitHub operations messages"""

        # Pull Requests
        PR_CREATING = "Creating pull request..."
        PR_CREATED = "✅ PR #{number} created: {url}"
        PR_UPDATED = "✅ PR #{number} updated"
        PR_MERGED = "✅ PR #{number} merged"
        PR_CLOSED = "✅ PR #{number} closed"
        PR_FAILED = "❌ Failed to create PR: {error}"
        PR_NOT_FOUND = "❌ PR not found: #{number}"

        # Reviews
        REVIEW_CREATING = "Creating review..."
        REVIEW_CREATED = "✅ Review submitted"
        REVIEW_FAILED = "❌ Failed to submit review: {error}"

        # Comments
        COMMENT_CREATING = "Adding comment..."
        COMMENT_CREATED = "✅ Comment added"
        COMMENT_FAILED = "❌ Failed to add comment: {error}"

        # Repository
        REPO_NOT_FOUND = "❌ Repository not found"
        REPO_ACCESS_DENIED = "❌ Access denied to repository"

        # Authentication
        AUTH_MISSING = "❌ GitHub token not found. Set GITHUB_TOKEN environment variable."
        AUTH_INVALID = "❌ Invalid GitHub token"

    # ═══════════════════════════════════════════════════════════════
    # Git Operations
    # ═══════════════════════════════════════════════════════════════

    class Git:
        """Git operations messages"""

        # Commits
        COMMITTING = "Committing changes..."
        COMMIT_SUCCESS = "✅ Committed: {sha}"
        COMMIT_FAILED = "❌ Commit failed: {error}"
        NO_CHANGES = "⚠️  No changes to commit"

        # Branches
        BRANCH_CREATING = "Creating branch: {name}"
        BRANCH_CREATED = "✅ Branch created: {name}"
        BRANCH_SWITCHING = "Switching to branch: {name}"
        BRANCH_SWITCHED = "✅ Switched to branch: {name}"
        BRANCH_DELETING = "Deleting branch: {name}"
        BRANCH_DELETED = "✅ Branch deleted: {name}"
        BRANCH_EXISTS = "⚠️  Branch already exists: {name}"
        BRANCH_NOT_FOUND = "❌ Branch not found: {name}"
        BRANCH_INVALID_NAME = "❌ Invalid branch name: {name}"

        # Push/Pull
        PUSHING = "Pushing to remote..."
        PUSH_SUCCESS = "✅ Pushed to {remote}/{branch}"
        PUSH_FAILED = "❌ Push failed: {error}"
        PULLING = "Pulling from remote..."
        PULL_SUCCESS = "✅ Pulled from {remote}/{branch}"
        PULL_FAILED = "❌ Pull failed: {error}"

        # Status
        STATUS_CLEAN = "✅ Working directory clean"
        STATUS_DIRTY = "⚠️  Uncommitted changes detected"

        # Repository
        NOT_A_REPO = "❌ Not a git repository"
        REPO_INIT = "Initializing git repository..."
        REPO_INITIALIZED = "✅ Git repository initialized"

    # ═══════════════════════════════════════════════════════════════
    # Jira Integration
    # ═══════════════════════════════════════════════════════════════

    class Jira:
        """Jira operations messages"""

        # Issues
        ISSUE_CREATING = "Creating Jira issue..."
        ISSUE_CREATED = "✅ Issue created: {key}"
        ISSUE_UPDATED = "✅ Issue updated: {key}"
        ISSUE_FAILED = "❌ Failed to create issue: {error}"
        ISSUE_NOT_FOUND = "❌ Issue not found: {key}"

        # Transitions
        TRANSITION_EXECUTING = "Transitioning issue to: {status}"
        TRANSITION_SUCCESS = "✅ Issue transitioned to: {status}"
        TRANSITION_FAILED = "❌ Failed to transition issue: {error}"

        # Authentication
        AUTH_MISSING = "❌ Jira credentials not found"
        AUTH_INVALID = "❌ Invalid Jira credentials"

    # ═══════════════════════════════════════════════════════════════
    # AI Integration
    # ═══════════════════════════════════════════════════════════════

    class AI:
        """AI operations messages"""

        # General
        PROCESSING = "🤖 AI processing..."
        COMPLETED = "✅ AI processing completed"
        FAILED = "❌ AI processing failed: {error}"

        # Reviews
        REVIEW_GENERATING = "🤖 Generating AI review..."
        REVIEW_GENERATED = "✅ AI review generated"

        # Code generation
        CODE_GENERATING = "🤖 Generating code..."
        CODE_GENERATED = "✅ Code generated"

        # Configuration
        PROVIDER_NOT_CONFIGURED = "❌ AI provider not configured"
        PROVIDER_INVALID = "❌ Invalid AI provider: {provider}"
        API_KEY_MISSING = "❌ API key not found for provider: {provider}"

        # Models
        MODEL_NOT_AVAILABLE = "❌ Model not available: {model}"
        RATE_LIMIT = "⚠️  Rate limit reached. Please try again later."

    # ═══════════════════════════════════════════════════════════════
    # Plugin System
    # ═══════════════════════════════════════════════════════════════

    class Plugin:
        """Plugin system messages"""

        # Discovery
        DISCOVERING = "Discovering plugins..."
        DISCOVERED = "✅ Discovered {count} plugin(s)"
        LOADING = "Loading plugin: {name}"
        LOADED = "✅ Plugin loaded: {name}"
        LOAD_FAILED = "❌ Failed to load plugin: {name} - {error}"

        # Listing
        LIST_TITLE = "Available Plugins"
        LIST_EMPTY = "No plugins found"
        LIST_ITEM = "  • {name} - {description}"

        # Errors
        NOT_FOUND = "❌ Plugin not found: {name}"
        INVALID_PLUGIN = "❌ Invalid plugin: {name}"
        DEPENDENCY_MISSING = "❌ Missing dependency for plugin {name}: {dependency}"

    # ═══════════════════════════════════════════════════════════════
    # Configuration
    # ═══════════════════════════════════════════════════════════════

    class Config:
        """Configuration messages"""

        # Loading
        LOADING = "Loading configuration..."
        LOADED = "✅ Configuration loaded"
        LOAD_FAILED = "❌ Failed to load configuration: {error}"

        # File operations
        FILE_NOT_FOUND = "❌ Configuration file not found: {path}"
        FILE_INVALID = "❌ Invalid configuration file: {error}"
        FILE_CREATED = "✅ Configuration file created: {path}"

        # Validation
        VALIDATING = "Validating configuration..."
        VALID = "✅ Configuration is valid"
        INVALID = "❌ Invalid configuration: {error}"

        # Settings
        SETTING_UPDATED = "✅ Setting updated: {key} = {value}"
        SETTING_INVALID = "❌ Invalid setting: {key}"

    # ═══════════════════════════════════════════════════════════════
    # User Prompts
    # ═══════════════════════════════════════════════════════════════

    class Prompts:
        """User input prompts"""

        # Confirmations
        CONFIRM_DELETE = "Are you sure you want to delete '{item}'?"
        CONFIRM_OVERWRITE = "'{path}' already exists. Overwrite?"
        CONFIRM_CONTINUE = "Continue?"
        CONFIRM_ABORT = "Abort operation?"

        # Input requests
        ENTER_NAME = "Enter name:"
        ENTER_TITLE = "Enter title:"
        ENTER_DESCRIPTION = "Enter description:"
        ENTER_BRANCH = "Enter branch name:"
        ENTER_MESSAGE = "Enter message:"

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

        # File system
        FILE_NOT_FOUND = "❌ File not found: {path}"
        FILE_READ_ERROR = "❌ Cannot read file: {path}"
        FILE_WRITE_ERROR = "❌ Cannot write file: {path}"
        DIRECTORY_NOT_FOUND = "❌ Directory not found: {path}"
        PERMISSION_DENIED = "❌ Permission denied: {path}"

        # Input validation
        INVALID_INPUT = "❌ Invalid input: {value}"
        MISSING_REQUIRED = "❌ Missing required field: {field}"
        INVALID_FORMAT = "❌ Invalid format: {value}"

        # Network
        NETWORK_ERROR = "❌ Network error: {error}"
        TIMEOUT = "❌ Operation timed out"
        CONNECTION_FAILED = "❌ Connection failed: {error}"

        # General
        UNKNOWN_ERROR = "❌ An unknown error occurred: {error}"
        NOT_IMPLEMENTED = "❌ Feature not implemented yet"
        OPERATION_CANCELLED = "🚫 Operation cancelled"


# Singleton instance for easy access
msg = Messages()
