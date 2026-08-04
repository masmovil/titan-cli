# Textual Workflow Steps Development Guide

This guide explains how to create workflow steps using the Textual TUI framework.

## Table of Contents

- [Basic Structure](#basic-structure)
- [Common Pitfalls](#common-pitfalls)
- [TextualComponents API](#textualcomponents-api)
- [Available Widgets](#available-widgets)
- [Complete Examples](#complete-examples)
- [Reference Files](#reference-files)

---

## Basic Structure

### Step Template

```python
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip, Exit

def my_step(ctx: WorkflowContext) -> WorkflowResult:
    """Step description."""

    # 1. Verify textual context is available
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # 2. Mark the beginning of the step (renders the step header)
    ctx.textual.begin_step("My Step")

    # 3. Step logic
    try:
        # Show progress with loading indicator
        with ctx.textual.loading("Processing..."):
            result = do_something()

        # Show result
        ctx.textual.panel("Success!", panel_type="success")

        # 4. Mark the end of the step before returning
        ctx.textual.end_step("success")
        return Success("Operation completed", metadata={"result": result})

    except Exception as e:
        ctx.textual.panel(str(e), panel_type="error")
        ctx.textual.end_step("error")
        return Error(str(e))
```

### Key Features

1. **Step Headers via begin_step/end_step**: Steps render their own header by calling `ctx.textual.begin_step("Title")` at the start and `ctx.textual.end_step("success" | "error" | "skip")` before returning (see `plugins/titan-plugin-git/titan_plugin_git/steps/commit_step.py` for a real example)
2. **Single Context**: Only `ctx.textual` for all UI interaction
3. **Loading Indicators**: Use context managers for long operations
4. **Textual Widgets**: Import widgets from `titan_cli.ui.tui.widgets`
5. **Thread-Safe**: All UI communication is automatically thread-safe

---

## Common Pitfalls

### ⚠️ Step Function Naming

**CRITICAL (project/user steps only)**: For steps loaded from `.titan/steps/` (`plugin: project`) or `~/.titan/steps/` (`plugin: user`), the function name must EXACTLY match the `step:` field in your workflow YAML.

**Plugin steps are different**: official plugin steps are mapped explicitly in the plugin's `get_steps()` dictionary, so the YAML `step:` name can differ from the function name (e.g. the git plugin maps `"create_commit"` to `create_git_commit_step`).

#### Example from Project Steps

**Project structure**:
```
.titan/
├── steps/
│   ├── github/
│   │   └── capture_pr_context.py  # Contains function
│   └── android/
│       └── detekt_check.py
└── workflows/
    └── create-pr-ai.yaml
```

**Function definition** (`.titan/steps/github/capture_pr_context.py`):
```python
def capture_pr_context(ctx: WorkflowContext) -> WorkflowResult:  # ← Function name
    """Capture PR context."""
    ...

__all__ = ["capture_pr_context"]  # ← Must match
```

**Workflow reference** (`.titan/workflows/create-pr-ai.yaml`):
```yaml
hooks:
  before_pr_generation:
    - id: capture-context
      name: "Capture PR Context"
      plugin: project
      step: capture_pr_context  # ← Must match function name EXACTLY
```

#### Common Mistakes

❌ **DON'T DO THIS**:
```python
# Function name has _step suffix
def capture_pr_context_step(ctx):  # ← Wrong!
    ...
```
```yaml
step: capture_pr_context  # ← Won't find the function
```

❌ **OR THIS**:
```python
def capture_pr_context(ctx):  # ← Function name
    ...
```
```yaml
step: capture_pr_context_step  # ← Wrong! Extra _step suffix
```

✅ **CORRECT**:
```python
def capture_pr_context(ctx):  # ← Exact match
    ...
```
```yaml
step: capture_pr_context  # ← Exact match
```

#### Why This Happens

The `ProjectStepSource` searches for functions by name using Python's `getattr()`:
```python
step_func = getattr(module, step_name, None)  # Looks for exact name
```

**Rule**: For project/user steps, function name = step name. No suffixes, no prefixes, exact match. Plugin steps are resolved through the `get_steps()` mapping instead.

---

## TextualComponents API

### Location
**File**: `/titan_cli/ui/tui/textual_components.py`
**Class**: `TextualComponents`

This is the main API available in workflow steps via `ctx.textual`. It provides methods for displaying content and requesting user input.

### Display Methods

#### Text Display Methods

These methods use the custom text widgets from `/titan_cli/ui/tui/widgets/text.py`:

```python
# Normal text
ctx.textual.text("Normal message")
ctx.textual.text("")  # Empty line for spacing

# Styled text
ctx.textual.bold_text("Important message")
ctx.textual.dim_text("Secondary information")

# Colored text
ctx.textual.primary_text("Primary color message")
ctx.textual.bold_primary_text("Bold primary message")
ctx.textual.success_text("Operation successful")
ctx.textual.error_text("Operation failed")
ctx.textual.warning_text("Warning message")
```

**Note**: There are no `italic_text()` / `dim_italic_text()` methods on `ctx.textual`. If you need italic text, mount the `ItalicText` / `DimItalicText` widgets directly (from `titan_cli.ui.tui.widgets`).

**IMPORTANT**: `text()` takes a single string argument (no `markup` parameter). Always use the specific styled methods instead:

```python
# ✅ CORRECT
ctx.textual.dim_text("(empty content)")
ctx.textual.success_text("Done!")

# ❌ WRONG - Don't use markup parameter
ctx.textual.text("(empty content)", markup="dim")
ctx.textual.text("Done!", markup="green")
```

#### Other Display Methods

##### `markdown(markdown_text: str)`
Renders markdown content.

```python
analysis = "## Summary\n\n- Point 1\n- Point 2"
ctx.textual.markdown(analysis)
```

##### `panel(text, panel_type="info", show_icon=True, use_markdown=False)`
Shows a bordered panel with consistent styling. Preferred over mounting the `Panel` widget manually.

```python
ctx.textual.panel("Operation completed successfully!", panel_type="success")
ctx.textual.panel("Warning: This action cannot be undone", panel_type="warning")
ctx.textual.panel("## Analysis\n\n- Point one", panel_type="info", use_markdown=True)
```

Panel types: `"info"`, `"success"`, `"warning"`, `"error"`.

##### `table(headers, rows, title="", full_width=True, cell_padding=1, zebra_stripes=False, show_header=True, show_cursor=True, cursor_type="row", row_height=1)`
Shows a table with consistent styling. Preferred over mounting the `Table` widget manually.

```python
ctx.textual.table(headers=["Name", "Value"], rows=[["foo", "bar"]])
ctx.textual.table(headers=headers, rows=rows, title="Results", row_height=2)
```

##### `show_diff_stat(formatted_files, formatted_summary, title="Changes summary:", use_panel=False)`
Renders a formatted `git diff --stat` display. Use alongside `format_diff_stat_display()` from `titan_plugin_git.operations`.

```python
from titan_plugin_git.operations import format_diff_stat_display

formatted_files, formatted_summary = format_diff_stat_display(stat_output)
ctx.textual.show_diff_stat(formatted_files, formatted_summary, "Changes in branch:")
ctx.textual.show_diff_stat(formatted_files, formatted_summary, "Changes made:", use_panel=True)
```

##### `mount(widget: Widget)`
Mounts any Textual widget to the output panel. Use for custom widgets; for panels and tables prefer the `panel()` / `table()` convenience methods above.

```python
from titan_cli.ui.tui.widgets import DimItalicText

ctx.textual.mount(DimItalicText("Secondary emphasis"))
```

##### `begin_step(title: str)`
Marks the beginning of a step (shows step header).

```python
ctx.textual.begin_step("Fetching PR Comments")
```

##### `end_step(status: str)`
Marks the end of a step. Status can be "success", "error", or "skip".

```python
ctx.textual.end_step("success")
ctx.textual.end_step("error")
ctx.textual.end_step("skip")
```

**Important**: The `end_step()` status is separate from the `WorkflowResult` you return:
- `Success` → typically use `end_step("success")`
- `Error` → typically use `end_step("error")`
- `Skip` → typically use `end_step("skip")`
- `Exit` → use `end_step("success")` or `end_step("skip")` depending on context

**WorkflowResult Types:**
- `Success(message, metadata={})` - Step completed successfully, continue workflow
- `Error(message)` - Step failed, stop workflow
- `Skip(message)` - Step was skipped, continue workflow
- `Exit(message)` - Exit workflow early in a controlled way (not an error)

```python
# Example: Exit when no data found (not an error, just nothing to do)
if not data:
    ctx.textual.dim_text("No data found")
    ctx.textual.end_step("success")  # ← Step itself succeeded
    return Exit("No data to process")  # ← But exit the workflow

# Example: User cancelled (skip this step)
if not user_confirmed:
    ctx.textual.warning_text("User cancelled")
    ctx.textual.end_step("skip")  # ← Mark as skipped
    return Exit("User cancelled")  # ← Exit the workflow
```

##### `scroll_to_end()`
Manually scrolls to the bottom of the output (rarely needed, see Scroll Behavior Guidelines).

```python
# Only use when showing large content + interactive widget immediately after
ctx.textual.markdown(very_large_content)
ctx.textual.scroll_to_end()  # Ensure user sees the next widget
choice = ctx.textual.ask_choice("What to do?", options)
```

### Interactive Methods (User Input)

#### `ask_text(question: str, default: str = "") -> Optional[str]`
Requests single-line text input from user (blocks until response).

```python
title = ctx.textual.ask_text("Enter PR title:", default="")
if not title:
    return Error("Title cannot be empty")
```

#### `ask_password(question: str) -> Optional[str]`
Requests a password/secret with hidden input (blocks until response). Raises `KeyboardInterrupt` if the user presses Escape.

```python
passphrase = ctx.textual.ask_password("Enter GPG passphrase:")
```

#### `ask_multiline(question: str, default: str = "") -> Optional[str]`
Requests multiline input (Enter to submit, Shift+Enter for new line).

```python
description = ctx.textual.ask_multiline(
    "Enter issue description:",
    default=""
)
```

#### `ask_confirm(question: str, default: bool = True) -> bool`
Requests Y/N confirmation.

```python
if ctx.textual.ask_confirm("Use AI-generated message?", default=True):
    # User said Yes
    pass
else:
    # User said No
    pass
```

#### `ask_multiselect(question: str, options: List[SelectionOption]) -> List[Any]`
Shows a multi-select list (spacebar to toggle, Enter to confirm).

```python
from titan_cli.ui.tui.widgets import SelectionOption

options = [
    SelectionOption(value="feature1", label="Feature 1"),
    SelectionOption(value="feature2", label="Feature 2", selected=True),
]

selected = ctx.textual.ask_multiselect("Select features:", options)
# Returns list of selected values: ["feature1", "feature2"]
```

#### `ask_choice(question: str, options: List[ChoiceOption]) -> Any`
Shows single-choice buttons.

```python
from titan_cli.ui.tui.widgets import ChoiceOption

options = [
    ChoiceOption(value="use", label="Use as-is", variant="primary"),
    ChoiceOption(value="edit", label="Edit", variant="default"),
    ChoiceOption(value="reject", label="Reject", variant="error"),
]

choice = ctx.textual.ask_choice("What to do?", options)
# Returns single value: "use", "edit", or "reject"
```

#### `ask_option(question: str, options: List[OptionItem]) -> Any`
Shows a styled option list with titles and descriptions (like workflow selection menu).

```python
from titan_cli.engine import OptionItem  # canonical import (widgets re-export is backward-compat)

options = [
    OptionItem(
        value=123,
        title="PR #123: Add new feature",
        description="Branch: feature/new → main"
    ),
    OptionItem(
        value=124,
        title="PR #124: Fix bug",
        description="Branch: fix/bug → develop"
    ),
]

selected = ctx.textual.ask_option("Select a PR:", options)
# Returns value: 123 or 124
```

### Utility Methods

#### `loading(message: str)` (Context Manager)
Shows a loading spinner during long operations.

```python
with ctx.textual.loading("Analyzing issue..."):
    analysis = jira_agent.analyze_issue(issue_key)
# Loading indicator disappears automatically
```

#### `launch_external_cli(cli_name: str, prompt: str = None, cwd: str = None) -> int`
Launches an external CLI, temporarily suspending the TUI.

```python
exit_code = ctx.textual.launch_external_cli(
    "claude",
    prompt="Fix this bug",
    cwd="/path/to/project"
)
```

### AI Content Review Flows

#### `ai_content_review_flow(content_title, content_body, ...) -> tuple[str, Optional[str], Optional[str]]`
Generic Use/Edit/Reject flow for reviewing AI-generated title + body content (PRs, issues, etc.). Shows a preview, offers three choices, and handles the edit loop.

Optional keyword args: `header_text`, `title_label`, `description_label`, `edit_instruction`, `confirm_question`, `choice_question`.

Returns `(choice, final_title, final_body)` where `choice` is `"use"`, `"edit"`, or `"reject"` (title/body are `None` on reject).

```python
choice, title, body = ctx.textual.ai_content_review_flow(
    content_title="feat: Add dark mode support",
    content_body="## Summary\n- Implemented theme switcher...",
    header_text="AI-Generated PR",
    title_label="PR Title:",
    description_label="PR Description:",
)

if choice == "reject":
    return Skip("User rejected AI content")
```

#### `ai_document_review_flow(document_title, document_content, ...) -> tuple[str, Optional[str]]`
Same Use/Edit/Reject flow for single long-form documents (release notes, reports). Uses a panel to preserve line breaks.

Optional keyword args: `header_text`, `title_label`, `edit_instruction`, `confirm_question`, `choice_question`.

Returns `(choice, final_content)`.

```python
choice, content = ctx.textual.ai_document_review_flow(
    document_title="Release Notes v26.8",
    document_content="# 26.8\n\n## Features\n- ...",
)
```

---

## Scroll Behavior Guidelines

### Overview

The Textual TUI uses a three-layer scroll management system to ensure consistent and predictable scrolling behavior.

### Rules

**1. Widgets NEVER auto-scroll**

Custom widgets (Panel, Markdown, Table, etc.) must NOT call scroll methods internally. This prevents:
- Conflicts between multiple widgets trying to control scroll position
- Unpredictable "tug of war" scroll behavior
- Widgets interrupting user's scroll position

```python
# ❌ BAD - Widget calling scroll
def markdown(self, markdown_text: str):
    md_widget = Markdown(markdown_text)
    target.mount(md_widget)
    self.output_widget._scroll_to_end()  # DON'T DO THIS

# ✅ GOOD - Widget just mounts, no scroll
def markdown(self, markdown_text: str):
    md_widget = Markdown(markdown_text)
    target.mount(md_widget)
    # Screen handles scroll when step completes
```

**2. Steps CAN manually scroll (rarely needed)**

Only use `ctx.textual.scroll_to_end()` in specific cases:
- Step displays very large content (exceeds full screen height)
- AND needs to immediately show an interactive widget below it
- User would otherwise need to manually scroll to see the next action

```python
# ✅ GOOD - Manual scroll for large content with interactive widget after
def ai_pr_description_step(ctx: WorkflowContext) -> WorkflowResult:
    # Show large PR description
    ctx.textual.markdown(large_pr_body)

    # Scroll so user sees the choice buttons below
    ctx.textual.scroll_to_end()

    # User now sees the interactive widget
    choice = ctx.textual.ask_choice("What would you like to do?", options)
```

```python
# ❌ BAD - Unnecessary manual scroll
def simple_step(ctx: WorkflowContext) -> WorkflowResult:
    ctx.textual.text("Processing...")
    ctx.textual.scroll_to_end()  # Not needed - screen will scroll when step ends
    return Success("Done")
```

**3. Screen ALWAYS auto-scrolls on step completion**

The workflow execution screen automatically scrolls to the bottom when:
- A step calls `ctx.textual.end_step()`
- This is the default behavior - no action needed from step developers
- Happens even if step already scrolled manually (redundant but safe)

### When to Use Manual Scroll

Use `ctx.textual.scroll_to_end()` only when ALL of these are true:

1. ✅ Content displayed is VERY large (multiple screen heights)
2. ✅ An interactive widget (ask_text, ask_confirm, ask_choice) comes immediately after
3. ✅ User needs to see the widget to continue the workflow
4. ✅ Without scroll, user would be stuck scrolling manually before they can interact

### Examples

**Example 1: Good use of manual scroll**
```python
# Large markdown preview + edit workflow
ctx.textual.markdown(very_large_pr_description)  # Multiple screens tall
ctx.textual.scroll_to_end()  # User needs to see buttons below
choice = ctx.textual.ask_choice("Use/Edit/Reject?", options)

if choice == "edit":
    edited = ctx.textual.ask_multiline("Edit content:", default=content)
    ctx.textual.scroll_to_end()  # After editing, show preview below
    ctx.textual.markdown(edited_preview)
    ctx.textual.scroll_to_end()  # Show confirmation button
    confirmed = ctx.textual.ask_confirm("Use this?")
```

**Example 2: No manual scroll needed**
```python
# Small/medium content - let screen handle it
ctx.textual.text("Processing...")
ctx.textual.panel("Result: Success", panel_type="success")
# Screen will auto-scroll when step ends
return Success("Done")
```

### Default Approach

**When in doubt, DON'T use manual scroll.** Let the screen handle it automatically. Manual scroll is only for exceptional cases with very large content and immediate user interaction.

---

## Available Widgets

### Location
**Directory**: `/titan_cli/ui/tui/widgets/`
**Exports**: `/titan_cli/ui/tui/widgets/__init__.py`

All widgets are imported from this package and can be mounted using `ctx.textual.mount()` or used in interactive methods.

### Display Widgets

#### Panel
Displays content in a bordered panel with different types/colors. In steps, prefer the `ctx.textual.panel()` convenience method instead of mounting this widget manually.

```python
# Preferred in steps
ctx.textual.panel("Operation successful", panel_type="success")
ctx.textual.panel("Error occurred", panel_type="error")
ctx.textual.panel("FYI: Something happened", panel_type="info")
ctx.textual.panel("Warning message", panel_type="warning")
```

**Implementation**: `/titan_cli/ui/tui/widgets/panel.py`

#### Table
Displays tabular data with headers. In steps, prefer the `ctx.textual.table()` convenience method instead of mounting this widget manually.

```python
headers = ["#", "Key", "Status", "Summary"]
rows = [
    ["1", "PROJ-123", "Open", "Fix login bug"],
    ["2", "PROJ-124", "In Progress", "Add dark mode"],
]

# Preferred in steps
ctx.textual.table(headers=headers, rows=rows, title="Issues")
```

**Implementation**: `/titan_cli/ui/tui/widgets/table.py`

#### Text Widgets
Various styled text widgets (used internally by `ctx.textual` methods).

```python
from titan_cli.ui.tui.widgets import (
    Text,              # Normal text
    BoldText,          # Bold
    DimText,           # Dimmed/secondary
    ItalicText,        # Italic
    DimItalicText,     # Dim + Italic
    PrimaryText,       # Primary color
    BoldPrimaryText,   # Bold + Primary
    SuccessText,       # Green
    ErrorText,         # Red
    WarningText,       # Yellow
)

# Direct usage (rarely needed - prefer ctx.textual methods)
ctx.textual.mount(DimText("Secondary information"))
ctx.textual.mount(SuccessText("Operation completed"))
```

**Implementation**: `/titan_cli/ui/tui/widgets/text.py`

**Note**: These are used internally by `ctx.textual.dim_text()`, `ctx.textual.success_text()`, etc. You should use those methods instead of mounting these widgets directly.

### Interactive Widgets

#### PromptInput
Single-line text input widget (used by `ctx.textual.ask_text()`).

```python
from titan_cli.ui.tui.widgets import PromptInput

# Used internally by ctx.textual.ask_text()
# Typically not instantiated directly
```

**Implementation**: `/titan_cli/ui/tui/widgets/prompt_input.py`

#### PromptTextArea
Multi-line text input widget (used by `ctx.textual.ask_multiline()`).

```python
from titan_cli.ui.tui.widgets import PromptTextArea

# Used internally by ctx.textual.ask_multiline()
# Typically not instantiated directly
```

**Implementation**: `/titan_cli/ui/tui/widgets/prompt_textarea.py`

#### PromptSelectionList
Multi-select list widget (used by `ctx.textual.ask_multiselect()`).

```python
from titan_cli.ui.tui.widgets import PromptSelectionList, SelectionOption

options = [
    SelectionOption(value="opt1", label="Option 1"),
    SelectionOption(value="opt2", label="Option 2"),
]

# Used via ctx.textual.ask_multiselect("Question?", options)
```

**Implementation**: `/titan_cli/ui/tui/widgets/prompt_selection_list.py`

#### PromptChoice
Single-choice button widget (used by `ctx.textual.ask_choice()`).

```python
from titan_cli.ui.tui.widgets import PromptChoice, ChoiceOption

options = [
    ChoiceOption(value="yes", label="Yes", variant="primary"),
    ChoiceOption(value="no", label="No", variant="default"),
]

# Used via ctx.textual.ask_choice("Question?", options)
```

**Implementation**: `/titan_cli/ui/tui/widgets/prompt_choice.py`

**Variants**: `"primary"`, `"default"`, `"success"`, `"warning"`, `"error"`

#### PromptOptionList
Styled option list with titles and descriptions (used by `ctx.textual.ask_option()`).

```python
from titan_cli.engine import OptionItem  # canonical import (widgets re-export is backward-compat)
from titan_cli.ui.tui.widgets import PromptOptionList

options = [
    OptionItem(
        value=1,
        title="Option 1",
        description="Description for option 1"
    ),
    OptionItem(
        value=2,
        title="Option 2",
        description="Description for option 2"
    ),
]

# Used via ctx.textual.ask_option("Select:", options)
```

**Implementation**: `/titan_cli/ui/tui/widgets/prompt_option_list.py`

**Use case**: When you need to show a list with both a title and description (like PR selection, workflow selection).

### Container Widgets

#### StepContainer
Container for step content with header.

```python
from titan_cli.ui.tui.widgets import StepContainer

# Used internally by TextualWorkflowExecutor
# Shows step number and title
```

**Implementation**: `/titan_cli/ui/tui/widgets/step_container.py`

#### Button
Styled button widget.

```python
from titan_cli.ui.tui.widgets import Button

# Used internally by PromptChoice
# Typically not used directly
```

**Implementation**: `/titan_cli/ui/tui/widgets/button.py`

---

## Complete Examples

### Example 1: Simple Step with Panel

```python
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip, Exit

def simple_step(ctx: WorkflowContext) -> WorkflowResult:
    """A simple step that shows a message."""
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    message = ctx.get("message", "Hello, World!")

    ctx.textual.panel(message, panel_type="success")

    return Success("Message displayed")
```

### Example 2: Step with User Input

```python
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip, Exit, Skip

def prompt_for_title_step(ctx: WorkflowContext) -> WorkflowResult:
    """Prompt user for a title."""
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Skip if already exists
    if ctx.get("title"):
        return Skip("Title already provided")

    try:
        title = ctx.textual.ask_text("Enter title:", default="")

        if not title:
            return Error("Title cannot be empty")

        ctx.textual.panel(f"Title set: {title}", panel_type="success")

        return Success("Title captured", metadata={"title": title})

    except (KeyboardInterrupt, EOFError):
        return Error("User cancelled")
```

### Example 3: Step with AI and Loading Indicator

```python
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip, Exit, Skip

def ai_analyze_step(ctx: WorkflowContext) -> WorkflowResult:
    """Analyze content using AI."""
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    # Check AI availability
    if not ctx.ai or not ctx.ai.is_available():
        ctx.textual.panel("AI not configured", panel_type="info")
        return Skip("AI not configured")

    content = ctx.get("content")
    if not content:
        ctx.textual.panel("No content to analyze", panel_type="error")
        return Error("No content to analyze")

    # Analyze with loading indicator
    from titan_cli.ai.models import AIMessage

    with ctx.textual.loading("Analyzing content with AI..."):
        response = ctx.ai.generate([
            AIMessage(role="user", content=f"Analyze this: {content}")
        ])

    analysis = response.content.strip()

    # Show result
    ctx.textual.text("")
    ctx.textual.bold_primary_text("AI Analysis:")
    ctx.textual.text("")
    ctx.textual.markdown(analysis)

    # Confirm usage
    use_analysis = ctx.textual.ask_confirm(
        "Use this analysis?",
        default=True
    )

    if not use_analysis:
        ctx.textual.warning_text("Analysis rejected")
        return Skip("User rejected analysis")

    ctx.textual.panel("Analysis accepted", panel_type="success")

    return Success("Analysis completed", metadata={"analysis": analysis})
```

### Example 4: Step with Table Results

```python
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip, Exit

def search_issues_step(ctx: WorkflowContext) -> WorkflowResult:
    """Search and display issues."""
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    if not ctx.jira:
        ctx.textual.panel("JIRA client not available", panel_type="error")
        return Error("JIRA client not available")

    query = ctx.get("query", "status = Open")

    # Search with loading
    with ctx.textual.loading("Searching issues..."):
        issues = ctx.jira.search_tickets(jql=query, max_results=50)

    if not issues:
        ctx.textual.panel("No issues found", panel_type="info")
        return Success("No issues found", metadata={"issues": []})

    # Show result
    ctx.textual.panel(f"Found {len(issues)} issues", panel_type="success")
    ctx.textual.text("")

    # Prepare table
    headers = ["#", "Key", "Status", "Summary"]
    rows = []
    for i, issue in enumerate(issues, 1):
        rows.append([
            str(i),
            issue.key,
            issue.status or "Unknown",
            (issue.summary or "No summary")[:60]
        ])

    # Render table
    ctx.textual.table(headers=headers, rows=rows, title="Issues")

    return Success(
        f"Found {len(issues)} issues",
        metadata={"issues": issues}
    )
```

### Example 5: Step with Error Handling

```python
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error, Skip, Exit
import requests

def fetch_data_step(ctx: WorkflowContext) -> WorkflowResult:
    """Fetch data from API."""
    if not ctx.textual:
        return Error("Textual UI context is not available for this step.")

    url = ctx.get("url")
    if not url:
        ctx.textual.panel("URL is required", panel_type="error")
        return Error("URL is required")

    try:
        # Show info
        ctx.textual.dim_text(f"Fetching from: {url}")

        # Fetch with loading
        with ctx.textual.loading(f"Fetching data from {url}..."):
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

        # Success
        ctx.textual.panel(
            f"Successfully fetched {len(data)} records",
            panel_type="success"
        )

        return Success("Data fetched", metadata={"data": data})

    except requests.RequestException as e:
        error_msg = f"Failed to fetch data: {e}"
        ctx.textual.panel(error_msg, panel_type="error")
        return Error(error_msg)
    except ValueError as e:
        error_msg = f"Invalid JSON response: {e}"
        ctx.textual.panel(error_msg, panel_type="error")
        return Error(error_msg)
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        error_msg = f"Unexpected error: {e}\n\n{error_detail}"
        ctx.textual.panel(error_msg, panel_type="error")
        return Error(error_msg)
```

---

## Reference Files

### Core Components
- **TextualComponents API**: `/titan_cli/ui/tui/textual_components.py`
- **Widgets**: `/titan_cli/ui/tui/widgets/`
- **Executor**: `/titan_cli/ui/tui/textual_workflow_executor.py`
- **Execution Screen**: `/titan_cli/ui/tui/screens/workflow_execution.py`

### Real Step Examples

**GitHub Plugin**:
- `/plugins/titan-plugin-github/titan_plugin_github/steps/github_prompt_steps.py`
- `/plugins/titan-plugin-github/titan_plugin_github/steps/ai_pr_step.py`
- `/plugins/titan-plugin-github/titan_plugin_github/steps/create_pr_step.py`

**Git Plugin**:
- `/plugins/titan-plugin-git/titan_plugin_git/steps/ai_commit_message_step.py`
- `/plugins/titan-plugin-git/titan_plugin_git/steps/commit_step.py`

**Jira Plugin**:
- `/plugins/titan-plugin-jira/titan_plugin_jira/steps/search_saved_query_step.py`
- `/plugins/titan-plugin-jira/titan_plugin_jira/steps/prompt_select_issue_step.py`
- `/plugins/titan-plugin-jira/titan_plugin_jira/steps/get_issue_step.py`
- `/plugins/titan-plugin-jira/titan_plugin_jira/steps/ai_analyze_issue_step.py`

---

## Benefits of the Textual Framework

1. **Unified UI**: Single context (`ctx.textual`) for all UI interaction
2. **Better UX**: Interactive Textual widgets superior to basic terminal output
3. **Integrated Progress**: `begin_step()`/`end_step()` render consistent step headers and status colors
4. **Loading Indicators**: Context managers for showing progress during long operations
5. **Low Boilerplate**: Convenience methods (`panel()`, `table()`, styled text) avoid repetitive formatting code
6. **Thread-Safe**: Automatic synchronization between execution threads and UI
7. **Markdown Support**: Native markdown rendering in the TUI
8. **External CLIs**: Can suspend TUI to launch external tools (claude, gemini, etc.)

---

## Extending the Textual System

This section explains how to add new widgets and methods to extend the Textual TUI framework.

### Creating a New Widget

Custom widgets should be created in `/titan_cli/ui/tui/widgets/` and follow Textual's widget patterns.

#### Step 1: Create Widget File

```python
# /titan_cli/ui/tui/widgets/my_custom_widget.py
from textual.widgets import Static
from textual.app import ComposeResult
from textual.containers import Vertical
from dataclasses import dataclass
from typing import Any, Callable, Optional

@dataclass
class MyCustomItem:
    """Data model for widget items."""
    value: Any
    label: str
    description: str = ""

class MyCustomWidget(Static):
    """
    Custom widget for specialized UI interaction.

    This widget shows a list of items with custom styling.
    """

    def __init__(
        self,
        question: str,
        items: list[MyCustomItem],
        on_submit: Optional[Callable[[Any], None]] = None,
        **kwargs
    ):
        """
        Args:
            question: Question to display
            items: List of items to show
            on_submit: Callback when user submits selection
        """
        super().__init__(**kwargs)
        self.question = question
        self.items = items
        self.on_submit = on_submit
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        """Compose the widget UI using Textual components."""
        from .text import BoldText, DimText

        # Show question
        yield BoldText(self.question)
        yield DimText("")  # Empty line

        # Show items
        with Vertical():
            for i, item in enumerate(self.items):
                # Use markup for inline styling
                prefix = "→ " if i == self.selected_index else "  "
                yield Static(f"{prefix}[bold]{item.label}[/bold]")
                if item.description:
                    yield Static(f"  [dim]{item.description}[/dim]")

    def on_key(self, event) -> None:
        """Handle keyboard input."""
        if event.key == "up":
            self.selected_index = max(0, self.selected_index - 1)
            self.refresh()
        elif event.key == "down":
            self.selected_index = min(len(self.items) - 1, self.selected_index + 1)
            self.refresh()
        elif event.key == "enter":
            # Submit selection
            selected_item = self.items[self.selected_index]
            if self.on_submit:
                self.on_submit(selected_item.value)
```

#### Step 2: Export Widget

Add to `/titan_cli/ui/tui/widgets/__init__.py`:

```python
from .my_custom_widget import MyCustomWidget, MyCustomItem

__all__ = [
    # ... existing exports
    "MyCustomWidget",
    "MyCustomItem",
]
```

#### Step 3: Use Widget in Steps

You can now use the widget directly:

```python
from titan_cli.ui.tui.widgets import MyCustomWidget, MyCustomItem

def my_step(ctx: WorkflowContext) -> WorkflowResult:
    items = [
        MyCustomItem(value=1, label="Option 1", description="First option"),
        MyCustomItem(value=2, label="Option 2", description="Second option"),
    ]

    # Direct usage (widget handles its own display)
    ctx.textual.mount(MyCustomWidget(
        question="Select an option:",
        items=items
    ))

    return Success("Widget displayed")
```

### Adding Methods to TextualComponents

To make widgets easier to use in steps, add convenience methods to `TextualComponents`.

#### Location
**File**: `/titan_cli/ui/tui/textual_components.py`

#### Pattern for Interactive Methods

All interactive methods must use threading and event containers for communication between threads.

```python
# In TextualComponents class

def ask_custom(self, question: str, items: list) -> Any:
    """
    Ask user to select from custom widget.

    Args:
        question: Question to display
        items: List of items to choose from

    Returns:
        Selected value or None if cancelled
    """
    from .widgets import MyCustomWidget, MyCustomItem

    # Container for thread-safe communication
    result_container = {"result": None, "ready": threading.Event()}

    def on_submit(value):
        """Callback when user submits."""
        result_container["result"] = value
        result_container["ready"].set()

    # Create widget with callback
    widget = MyCustomWidget(
        question=question,
        items=items,
        on_submit=on_submit
    )

    # Mount widget on UI thread
    target = self._get_current_output_target()
    self.app.call_from_thread(target.mount, widget)

    # Wait for user response with timeout for Ctrl+C handling
    try:
        while not result_container["ready"].wait(timeout=0.5):
            pass
    except KeyboardInterrupt:
        result_container["result"] = None

    return result_container["result"]
```

#### KeyboardInterrupt Handling

**CRITICAL**: All interactive methods MUST handle Ctrl+C using a timeout loop:

```python
# ✅ CORRECT - Timeout allows KeyboardInterrupt to be caught
try:
    while not result_container["ready"].wait(timeout=0.5):
        pass
except KeyboardInterrupt:
    result_container["result"] = None

# ❌ WRONG - Blocks forever, Ctrl+C doesn't work
result_container["ready"].wait()
```

**Why this pattern:**
- Python can only process KeyboardInterrupt during active code execution
- `wait()` with no timeout blocks in C code, preventing interrupt handling
- `wait(timeout=0.5)` returns to Python every 0.5s, allowing interrupts
- Wrapping in try/except catches Ctrl+C and returns None gracefully

#### Usage After Adding Method

```python
def my_step(ctx: WorkflowContext) -> WorkflowResult:
    from titan_cli.ui.tui.widgets import MyCustomItem

    items = [
        MyCustomItem(value=1, label="Option 1", description="First"),
        MyCustomItem(value=2, label="Option 2", description="Second"),
    ]

    # Now much cleaner to use!
    selected = ctx.textual.ask_custom("Select an option:", items)

    if not selected:
        return Error("No selection made")

    return Success(f"Selected: {selected}")
```

### Common Extension Patterns

#### Pattern 1: Generic AI Integration

Always use `AIMessage` for model-agnostic AI calls:

```python
from titan_cli.ai.models import AIMessage

def ai_helper_step(ctx: WorkflowContext) -> WorkflowResult:
    if not ctx.ai or not ctx.ai.is_available():
        return Skip("AI not configured")

    # Build messages
    messages = [
        AIMessage(role="user", content="Analyze this...")
    ]

    # Generate (works with Claude, Gemini, any configured provider)
    with ctx.textual.loading("Generating..."):
        response = ctx.ai.generate(messages)

    result = response.content.strip()
    ctx.textual.markdown(result)

    return Success("AI analysis complete")
```

#### Pattern 2: Empty Content Handling

Always check for empty/None content from APIs:

```python
# ✅ CORRECT - Handle empty content gracefully
if content and content.strip():
    ctx.textual.markdown(content)
else:
    ctx.textual.dim_text("(no content)")

# ❌ WRONG - May crash on None or show empty space
ctx.textual.markdown(content)
```

#### Pattern 3: API Field Variations

Some APIs return different field names for the same data. Try multiple fields:

```python
# GitHub API line numbers
line = data.get("line") or data.get("original_line") or data.get("start_line")

# Author information
author = data.get("user") or data.get("author") or {}
```

#### Pattern 4: Recursive Data Structures

Use recursion for building hierarchical structures:

```python
def build_comment_tree(comments: list, parent_id: int = None) -> list:
    """Recursively build comment thread tree."""
    tree = []

    for comment in comments:
        if comment.parent_id == parent_id:
            # This comment belongs at this level
            tree.append(comment)

            # Recursively find children
            children = build_comment_tree(comments, comment.id)
            if children:
                comment.children = children

    return tree
```

### Widget Best Practices

#### 1. Use Dataclasses for Item Models

```python
@dataclass
class OptionItem:
    """Clear data structure for widget items."""
    value: Any
    title: str
    description: str = ""
```

#### 2. Accept Callbacks for Events

```python
def __init__(self, on_submit: Optional[Callable] = None):
    self.on_submit = on_submit
```

#### 3. Use Textual Markup for Styling

```python
# ✅ CORRECT - Use markup strings
yield Static(f"[bold]{title}[/bold]")
yield Static(f"[dim]{description}[/dim]")

# ❌ WRONG - Don't create multiple styled widgets
yield BoldText(title)  # Unnecessary - markup is cleaner
```

#### 4. Handle Focus and Keyboard Events

```python
def on_mount(self) -> None:
    """Set focus when widget mounts."""
    self.focus()

def on_key(self, event: Key) -> None:
    """Handle keyboard input."""
    if event.key == "enter":
        self.submit()
    elif event.key == "escape":
        self.cancel()
```

### Testing New Widgets

Test widgets interactively by creating a test step:

```python
# Test in a workflow step
def test_widget_step(ctx: WorkflowContext) -> WorkflowResult:
    if not ctx.textual:
        return Error("No Textual context")

    from titan_cli.ui.tui.widgets import MyCustomWidget, MyCustomItem

    items = [
        MyCustomItem(value=1, label="Test 1", description="First test"),
        MyCustomItem(value=2, label="Test 2", description="Second test"),
    ]

    ctx.textual.mount(MyCustomWidget("Test question:", items))

    return Success("Widget test complete")
```

---

**Last updated**: 2026-08-04
