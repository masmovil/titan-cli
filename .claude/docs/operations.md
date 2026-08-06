# Operations Pattern Guide

**Complete guide for implementing the Operations Pattern in Titan CLI plugins**

Last updated: 2026-08-04

---

## Overview

The **Operations Pattern** separates business logic from UI orchestration for cleaner, testable, and maintainable code.

### Why Operations?

**Before Operations:**
```python
# ❌ BAD: Business logic mixed with UI
def my_step(ctx):
    ctx.textual.begin_step("Process Data")

    # Business logic mixed with UI
    data = ctx.get("input")
    if not data:
        ctx.textual.error_text("No data")
        return Error("No data")

    # Complex parsing logic
    items = []
    for line in data.split('\n'):
        if '|' in line:
            parts = line.split('|')
            items.append(parts[0].strip())

    # More business logic...
    filtered = [x for x in items if len(x) > 5]

    ctx.textual.success_text(f"Processed {len(filtered)} items")
    return Success("Done", metadata={"items": filtered})
```

**After Operations:**
```python
# ✅ GOOD: Clean separation
def my_step(ctx):
    ctx.textual.begin_step("Process Data")

    data = ctx.get("input")
    if not data:
        ctx.textual.error_text("No data")
        return Error("No data")

    # Call tested business logic
    items = parse_data(data)
    filtered = filter_items(items, min_length=5)

    ctx.textual.success_text(f"Processed {len(filtered)} items")
    return Success("Done", metadata={"items": filtered})
```

---

## Architecture

### Directory Structure

```
plugins/titan-plugin-{name}/
├── titan_plugin_{name}/
│   ├── operations/              # NEW: Pure business logic
│   │   ├── __init__.py         # Export all operations
│   │   ├── {domain}_operations.py
│   │   └── ...
│   ├── steps/                   # UI orchestration only
│   │   ├── {step_name}_step.py
│   │   └── ...
│   └── ...
├── tests/
│   ├── operations/              # NEW: Unit tests for operations
│   │   ├── test_{domain}_operations.py
│   │   └── ...
│   └── ...
```

### Responsibilities

| Layer | Responsibility | Can Access | Cannot Access |
|-------|---------------|------------|---------------|
| **Operations** | Business logic, data transformation | - Pure Python <br>- Data structures <br>- Other operations | - UI (ctx.textual) <br>- Workflow context <br>- Display logic |
| **Steps** | UI orchestration, user interaction | - ctx.textual <br>- ctx.data <br>- Operations | - Complex logic <br>- Data parsing <br>- Algorithms |

---

## Implementation Guide

### Step 1: Identify Business Logic

Look for code that does NOT involve UI:

**Extract to Operations:**
- ✅ Data parsing and transformation
- ✅ Validation logic
- ✅ Calculations and algorithms
- ✅ String manipulation
- ✅ List/dict processing
- ✅ API response parsing

**Keep in Steps:**
- ❌ `ctx.textual.text()` calls
- ❌ User prompts (`ask_text`, `ask_confirm`)
- ❌ Loading indicators
- ❌ Error message display
- ❌ Widget mounting

### Step 2: Create Operations Module

```python
# plugins/titan-plugin-github/titan_plugin_github/operations/issue_operations.py
"""
Issue Operations

Pure business logic for GitHub issue functionality.
These functions can be used by any step and are easily testable.
"""

from typing import List, Tuple


def parse_comma_separated_list(input_string: str) -> List[str]:
    """
    Parse a comma-separated string into a list of trimmed non-empty items.

    Args:
        input_string: Comma-separated string (e.g., "bug, feature, help wanted")

    Returns:
        List of trimmed non-empty strings
    """
    if not input_string or not input_string.strip():
        return []

    items = [item.strip() for item in input_string.split(",") if item.strip()]
    return items


def filter_valid_labels(
    selected_labels: List[str],
    available_labels: List[str]
) -> Tuple[List[str], List[str]]:
    """
    Filter selected labels to separate valid and invalid ones.

    Args:
        selected_labels: Labels selected by the user
        available_labels: Labels that exist in the repository

    Returns:
        Tuple of (valid_labels, invalid_labels)
    """
    valid = []
    invalid = []

    for label in selected_labels:
        if label in available_labels:
            valid.append(label)
        else:
            invalid.append(label)

    return valid, invalid


__all__ = [
    "parse_comma_separated_list",
    "filter_valid_labels",
]
```

### Step 3: Export from __init__.py

```python
# plugins/titan-plugin-github/titan_plugin_github/operations/__init__.py
"""
GitHub Plugin Operations

Pure business logic functions that can be used in steps or called programmatically.
All functions here are UI-agnostic and can be unit tested independently.
"""

from .issue_operations import (
    parse_comma_separated_list,
    filter_valid_labels,
)

from .pr_operations import (
    fetch_pr_threads,
    fetch_pr_general_comments,
    split_titan_review_body,
    build_quote_reply,
)

__all__ = [
    # Issue operations
    "parse_comma_separated_list",
    "filter_valid_labels",

    # PR operations
    "fetch_pr_threads",
    "fetch_pr_general_comments",
    "split_titan_review_body",
    "build_quote_reply",
]
```

### Step 4: Write Unit Tests

```python
# plugins/titan-plugin-github/tests/operations/test_issue_operations.py
"""
Tests for Issue Operations

Tests for pure business logic related to GitHub issues.
"""

from titan_plugin_github.operations.issue_operations import (
    parse_comma_separated_list,
    filter_valid_labels,
)


class TestParseCommaSeparatedList:
    """Tests for parse_comma_separated_list function."""

    def test_parse_simple_list(self):
        """Should parse simple comma-separated list."""
        result = parse_comma_separated_list("bug, feature, help wanted")
        assert result == ["bug", "feature", "help wanted"]

    def test_parse_with_extra_spaces(self):
        """Should trim extra spaces from items."""
        result = parse_comma_separated_list("  bug  ,  feature  ")
        assert result == ["bug", "feature"]

    def test_parse_empty_string(self):
        """Should return empty list for empty string."""
        result = parse_comma_separated_list("")
        assert result == []


class TestFilterValidLabels:
    """Tests for filter_valid_labels function."""

    def test_all_labels_valid(self):
        """Should return all labels as valid when they exist."""
        valid, invalid = filter_valid_labels(
            selected_labels=["bug", "feature"],
            available_labels=["bug", "feature", "help wanted"]
        )
        assert valid == ["bug", "feature"]
        assert invalid == []

    def test_some_labels_invalid(self):
        """Should separate valid and invalid labels."""
        valid, invalid = filter_valid_labels(
            selected_labels=["bug", "invalid"],
            available_labels=["bug", "feature"]
        )
        assert valid == ["bug"]
        assert invalid == ["invalid"]
```

**Target: 100% test coverage on operations**

### Step 5: Refactor Steps to Use Operations

```python
# plugins/titan-plugin-github/titan_plugin_github/steps/issue_steps.py
from titan_cli.engine import WorkflowContext, WorkflowResult, Success, Error
from titan_cli.core.result import ClientSuccess, ClientError
from ..operations import filter_valid_labels  # Import operations


def create_issue_step(ctx: WorkflowContext) -> WorkflowResult:
    ctx.textual.begin_step("Create Issue")

    # Get data from context
    labels = ctx.get("labels", [])

    # Use operation for business logic
    if labels and ctx.github:
        # list_labels() returns ClientResult[List[str]] - pattern match it
        match ctx.github.list_labels():
            case ClientSuccess(data=available_labels):
                valid_labels, invalid_labels = filter_valid_labels(labels, available_labels)

                # UI only: Display results
                if invalid_labels:
                    ctx.textual.warning_text(f"Skipping invalid labels: {', '.join(invalid_labels)}")

                labels = valid_labels
            case ClientError(error_message=err):
                ctx.textual.error_text(err)
                return Error(err)

    # Continue with step...
    ctx.textual.end_step("success")
    return Success("Issue created")
```

#### Operation Import Aliases in Steps

When a step imports an operation with the same name as the step, or when the
layer boundary would otherwise be unclear, alias the imported operation with a
descriptive `_operation` suffix.

```python
# ✅ GOOD: clear step vs operation boundary
from ..operations.manifest_operations import (
    build_change_manifest as build_change_manifest_operation,
)


def build_change_manifest(ctx: WorkflowContext) -> WorkflowResult:
    manifest = build_change_manifest_operation(pr, files)
```

Avoid private-looking or abbreviated aliases for imported operations:

```python
# ❌ BAD: looks private and hides intent
from ..operations.manifest_operations import build_change_manifest as _build
from ..operations.review_strategy_operations import score_review_candidates as _score
```

Keep operation function names natural in `operations/`; do not add an
`_operation` suffix to every operation definition just to avoid aliases. The
suffix is for step-layer imports where it clarifies orchestration vs pure
business logic.

---

## Best Practices

### ✅ DO

1. **Write docstrings describing args and returns (NO doctest examples)**
   ```python
   def my_operation(data: str) -> List[str]:
       """
       Brief description.

       Args:
           data: Description

       Returns:
           Description
       """
   ```
   Do NOT add `Examples:` / doctest blocks - the project doesn't run doctests
   and verbose mocks make docstrings unreadable. Real examples live in `/tests`
   (see "Docstrings - NO Examples" in [plugin-architecture.md](plugin-architecture.md)).

2. **Make operations pure functions** (no side effects)
   ```python
   # ✅ GOOD: Pure function
   def calculate_total(items: List[int]) -> int:
       return sum(items)

   # ❌ BAD: Side effects
   def calculate_total(items: List[int]) -> int:
       print("Calculating...")  # Side effect!
       return sum(items)
   ```

3. **Return tuples for multiple values**
   ```python
   def split_data(text: str) -> Tuple[List[str], List[str]]:
       valid = []
       invalid = []
       # ... processing
       return valid, invalid
   ```

4. **Handle edge cases**
   ```python
   def parse_list(text: str) -> List[str]:
       if not text or not text.strip():
           return []  # Handle empty input
       return text.split(",")
   ```

### ❌ DON'T

1. **Don't access UI in operations**
   ```python
   # ❌ BAD
   def process_data(ctx, data):
       ctx.textual.text("Processing...")  # NO!
       return data

   # ✅ GOOD
   def process_data(data: str) -> str:
       # Pure logic only
       return data.strip()
   ```

2. **Don't pass context to operations**
   ```python
   # ❌ BAD
   def my_operation(ctx: WorkflowContext):
       data = ctx.get("data")  # NO!

   # ✅ GOOD
   def my_operation(data: str):
       # Explicit parameters
   ```

3. **Don't duplicate logic**
   ```python
   # ❌ BAD: Same logic in multiple places
   # step1.py
   items = [x.strip() for x in data.split(",") if x.strip()]

   # step2.py
   items = [x.strip() for x in data.split(",") if x.strip()]  # Duplicate!

   # ✅ GOOD: Extract to operation
   from ..operations import parse_comma_separated_list
   items = parse_comma_separated_list(data)
   ```

---

## Real-World Examples

### Example 1: Git Diff Formatting

**Before (Duplicated in 2 functions):**
```python
# diff_summary_step.py - Lines 39-72
for line in stat_output.split('\n'):
    if not line.strip():
        continue
    if '|' in line:
        parts = line.split('|')
        filename = parts[0].strip()
        stats = '|'.join(parts[1:]) if len(parts) > 1 else ''
        file_lines.append((filename, stats))
        max_filename_len = max(max_filename_len, len(filename))
# ... 30 more lines of identical code ...
```

**After (Extracted to operation):**
```python
# operations/diff_operations.py
def format_diff_stat_display(stat_output: str) -> Tuple[List[str], List[str]]:
    """Format git diff --stat output for display with colors and alignment."""
    # ... all the logic here ...
    return formatted_files, formatted_summary

# diff_summary_step.py
from ..operations import format_diff_stat_display

formatted_files, formatted_summary = format_diff_stat_display(stat_output)
for line in formatted_files:
    ctx.textual.text(f"  {line}")
```

**Result:** 48 lines eliminated, 0% duplication

### Example 2: JQL Variable Substitution

**Before:**
```python
# search_jql_step.py
import re

def replace_var(match):
    var_name = match.group(1)
    value = ctx.get(var_name)
    if value is None:
        return match.group(0)
    return str(value)

jql = re.sub(r'\$\{([^}]+)\}', replace_var, jql)
```

**After:**
```python
# operations/jql_operations.py
def substitute_jql_variables(jql: str, context_data: Dict[str, any]) -> str:
    """Substitute variables in JQL query with values from context."""
    def replace_var(match):
        var_name = match.group(1)
        value = context_data.get(var_name)
        if value is None:
            return match.group(0)
        return str(value)
    return re.sub(r'\$\{([^}]+)\}', replace_var, jql)

# search_jql_step.py
from ..operations import substitute_jql_variables

jql = substitute_jql_variables(jql, ctx.data)
```

**Result:** Reusable, testable, clear

---

## Testing Strategy

### Unit Tests for Operations

```bash
# Run tests
poetry run pytest plugins/titan-plugin-{name}/tests/operations/ -v

# Check coverage
poetry run pytest plugins/titan-plugin-{name}/tests/operations/ \
    --cov=plugins/titan-plugin-{name}/titan_plugin_{name}/operations \
    --cov-report=term-missing
```

**Target: 100% coverage**

### Example Test Structure

```python
class TestMyOperation:
    """Tests for my_operation function."""

    def test_normal_case(self):
        """Should handle normal input."""
        result = my_operation("test")
        assert result == expected

    def test_edge_case_empty(self):
        """Should handle empty input."""
        result = my_operation("")
        assert result == []

    def test_edge_case_none(self):
        """Should handle None input."""
        result = my_operation(None)
        assert result == default_value

    def test_complex_input(self):
        """Should handle complex nested data."""
        # ...
```

---

## Migration Checklist

When refactoring an existing step:

- [ ] Identify all business logic (see "Step 1")
- [ ] Create operations module with descriptive name
- [ ] Extract each piece of logic to a function
- [ ] Write docstrings (Args/Returns, no doctest examples)
- [ ] Write unit tests (aim for 100%)
- [ ] Update step to import and use operations
- [ ] Verify step syntax with `python3 -m py_compile`
- [ ] Run operations tests
- [ ] Check for code duplication (use grep/search)
- [ ] Update `operations/__init__.py` exports

---

## Current Status (2026-08-04)

**Plugins with Operations:**

| Plugin | Operations Modules | Public Functions | Tests |
|--------|-------------------|------------------|-------|
| GitHub | 18 modules | 92 funcs | 207 tests |
| Git | 3 modules | 14 funcs | 75 tests |
| Jira | 5 modules | 19 funcs | 73 tests |
| **Total** | **26 modules** | **125 funcs** | **355 tests** |

**Benefits Achieved:**
- 295 lines of duplicated code eliminated
- 100% of business logic now testable
- Steps 30-40% smaller and cleaner
- Zero logic duplication across plugins

---

## Questions?

- See examples in existing plugins: `plugins/titan-plugin-{name}/titan_plugin_{name}/operations/` (e.g. `plugins/titan-plugin-github/titan_plugin_github/operations/`)
- Check test examples: `plugins/titan-plugin-{github,git,jira}/tests/operations/`
- Review CLAUDE.md for architecture overview

**Remember: When in doubt, extract to operations!**
