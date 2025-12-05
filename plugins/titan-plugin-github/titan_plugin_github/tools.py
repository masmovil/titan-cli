"""
TAP-compatible tools for GitHub PR review agents.

These tools allow AI agents to interact with GitHub PRs autonomously.
"""

from typing import Any, Dict
from dataclasses import dataclass, field


# Simplified TitanTool classes (matching test structure)
@dataclass
class ToolParameter:
    """Metadata for a tool parameter."""
    type_hint: str
    description: str = ""
    required: bool = True


@dataclass
class ToolSchema:
    """Schema definition for a tool."""
    name: str
    description: str
    parameters: Dict[str, ToolParameter] = field(default_factory=dict)


class TitanTool:
    """Base class for Titan tools."""

    def __init__(self, schema: ToolSchema):
        self.schema = schema
        self.name = schema.name
        self.description = schema.description

    def execute(self, **kwargs) -> Any:
        """Execute the tool - to be overridden."""
        raise NotImplementedError


# GitHub PR Tools
class GetPRFilesTool(TitanTool):
    """Tool to get list of files changed in a PR."""

    def __init__(self, github_client, pr_number: int):
        schema = ToolSchema(
            name="get_pr_files",
            description="Gets the list of files changed in the pull request",
            parameters={}
        )
        super().__init__(schema)
        self.github_client = github_client
        self.pr_number = pr_number

    def execute(self) -> str:
        """Get PR files."""
        try:
            files = self.github_client.get_pull_request_files(self.pr_number)
            if not files:
                return "No files found in this PR"

            result = f"Files changed in PR #{self.pr_number}:\n\n"
            for file_info in files:
                filename = file_info.get('filename', 'unknown')
                status = file_info.get('status', 'modified')
                additions = file_info.get('additions', 0)
                deletions = file_info.get('deletions', 0)
                result += f"- {filename} ({status}): +{additions} -{deletions}\n"

            return result
        except Exception as e:
            return f"Error fetching PR files: {str(e)}"


class GetPRCommentsTool(TitanTool):
    """Tool to get existing comments on a PR."""

    def __init__(self, github_client, pr_number: int):
        schema = ToolSchema(
            name="get_pr_comments",
            description="Gets existing review comments on the pull request",
            parameters={}
        )
        super().__init__(schema)
        self.github_client = github_client
        self.pr_number = pr_number

    def execute(self) -> str:
        """Get PR comments."""
        try:
            comments = self.github_client.get_pull_request_comments(self.pr_number)
            if not comments:
                return "No comments found on this PR"

            result = f"Comments on PR #{self.pr_number}:\n\n"
            for comment in comments[:10]:  # Limit to 10 most recent
                author = comment.get('user', {}).get('login', 'unknown')
                body = comment.get('body', '')
                created = comment.get('created_at', '')
                result += f"**{author}** ({created}):\n{body}\n\n"

            if len(comments) > 10:
                result += f"... and {len(comments) - 10} more comments"

            return result
        except Exception as e:
            return f"Error fetching PR comments: {str(e)}"


class AnalyzeCodeTool(TitanTool):
    """Tool to analyze code for common issues."""

    def __init__(self):
        schema = ToolSchema(
            name="analyze_code",
            description="Analyzes code snippet for potential issues",
            parameters={
                "code": ToolParameter(
                    type_hint="str",
                    description="Code snippet to analyze",
                    required=True
                ),
                "language": ToolParameter(
                    type_hint="str",
                    description="Programming language (e.g., 'python', 'javascript')",
                    required=False
                )
            }
        )
        super().__init__(schema)

    def execute(self, code: str, language: str = "unknown") -> str:
        """Analyze code snippet."""
        issues = []

        # Simple heuristic analysis
        if "TODO" in code or "FIXME" in code:
            issues.append("Contains TODO/FIXME comments that should be addressed")

        if "print(" in code and language == "python":
            issues.append("Contains print statements (consider using logging)")

        if "console.log(" in code and language == "javascript":
            issues.append("Contains console.log (consider removing for production)")

        if "eval(" in code:
            issues.append("⚠️ SECURITY: Uses eval() which can be dangerous")

        if "exec(" in code:
            issues.append("⚠️ SECURITY: Uses exec() which can be dangerous")

        # Check for long lines
        lines = code.split('\n')
        long_lines = [i + 1 for i, line in enumerate(lines) if len(line) > 120]
        if long_lines:
            issues.append(f"Lines exceed 120 characters: {long_lines[:5]}")

        # Check for deep nesting
        max_indent = max((len(line) - len(line.lstrip()) for line in lines if line.strip()), default=0)
        if max_indent > 16:  # 4 levels of indentation
            issues.append(f"Deep nesting detected (max indent: {max_indent // 4} levels)")

        if not issues:
            return "✓ No obvious issues found in code snippet"

        result = f"Analysis of {language} code:\n\n"
        for issue in issues:
            result += f"- {issue}\n"

        return result


class SuggestImprovementTool(TitanTool):
    """Tool to suggest code improvements."""

    def __init__(self):
        schema = ToolSchema(
            name="suggest_improvement",
            description="Suggests improvements for code quality",
            parameters={
                "code": ToolParameter(
                    type_hint="str",
                    description="Code snippet to improve",
                    required=True
                ),
                "issue": ToolParameter(
                    type_hint="str",
                    description="The issue to address",
                    required=True
                )
            }
        )
        super().__init__(schema)

    def execute(self, code: str, issue: str) -> str:
        """Suggest improvements."""
        suggestions = []

        if "print" in issue.lower() and "print(" in code:
            suggestions.append("""
Replace print statements with proper logging:
```python
import logging
logger = logging.getLogger(__name__)
logger.info("your message")
```
""")

        if "console.log" in issue.lower() and "console.log(" in code:
            suggestions.append("""
Remove console.log or use proper logging:
```javascript
// For debugging, consider using a logger
// For production, remove these statements
```
""")

        if "eval" in issue.lower() or "exec" in issue.lower():
            suggestions.append("""
⚠️ CRITICAL: Replace eval()/exec() with safer alternatives:
- Use ast.literal_eval() for parsing Python literals
- Use json.loads() for JSON data
- Refactor to use explicit function calls
""")

        if "long line" in issue.lower():
            suggestions.append("""
Break long lines for better readability:
- Use parentheses for implicit line continuation
- Break after operators
- Use Black or similar formatter
""")

        if "nesting" in issue.lower():
            suggestions.append("""
Reduce nesting depth:
- Extract nested logic into separate functions
- Use early returns to reduce indentation
- Consider using guard clauses
""")

        if not suggestions:
            return f"Consider refactoring to address: {issue}"

        result = f"Suggestions for '{issue}':\n\n"
        for suggestion in suggestions:
            result += suggestion + "\n"

        return result
