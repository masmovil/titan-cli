# plugins/titan-plugin-jira/titan_plugin_jira/formatters/markdown_formatter.py
"""Markdown formatter for JIRA issue analysis."""

from typing import List, Optional
from pathlib import Path
from dataclasses import asdict
from ..agents.jira_agent import IssueAnalysis


class IssueAnalysisMarkdownFormatter:
    """
    Formats IssueAnalysis into markdown for display.

    This class separates presentation logic from business logic,
    making it easy to:
    - Modify output format without touching agent code
    - Test formatting independently
    - Add other formatters (HTML, JSON, etc.) in the future
    - Optionally use Jinja2 templates for custom formatting

    Example:
        >>> # Use built-in formatter (default)
        >>> formatter = IssueAnalysisMarkdownFormatter()
        >>> markdown = formatter.format(analysis)

        >>> # Use custom Jinja2 template
        >>> formatter = IssueAnalysisMarkdownFormatter(template_path="custom.md.j2")
        >>> markdown = formatter.format(analysis)
    """

    def __init__(self, template_path: Optional[str] = None):
        """
        Initialize the formatter.

        Args:
            template_path: Optional path to Jinja2 template file.
                          If None, uses built-in Python formatter.
                          If provided, must be relative to config/templates/
        """
        self.template = None
        if template_path:
            self.template = self._load_template(template_path)

    def _load_template(self, template_name: str):
        """
        Load Jinja2 template from config/templates/.

        Args:
            template_name: Template filename (e.g., "issue_analysis.md.j2")

        Returns:
            Jinja2 Template object or None if Jinja2 not available
        """
        try:
            from jinja2 import Environment, FileSystemLoader
        except ImportError:
            # Jinja2 not installed, fall back to built-in formatter
            return None

        try:
            # Templates directory is relative to this file
            # This works both in development and when installed
            templates_dir = Path(__file__).parent.parent / "config" / "templates"

            if not templates_dir.exists():
                return None

            env = Environment(loader=FileSystemLoader(str(templates_dir)))
            return env.get_template(template_name)
        except Exception:
            # Template not found or other error, fall back to built-in formatter
            # Silently fail and use built-in formatter
            return None

    def format(self, analysis: IssueAnalysis) -> str:
        """
        Format IssueAnalysis into markdown.

        Args:
            analysis: IssueAnalysis object from JiraAgent

        Returns:
            Formatted markdown string
        """
        if self.template:
            # Use Jinja2 template
            return self._format_with_template(analysis)
        else:
            # Use built-in Python formatter
            return self._format_builtin(analysis)

    def _format_with_template(self, analysis: IssueAnalysis) -> str:
        """
        Format using Jinja2 template.

        Args:
            analysis: IssueAnalysis object

        Returns:
            Rendered markdown string
        """
        # Convert dataclass to dict for template
        analysis_dict = asdict(analysis)
        return self.template.render(**analysis_dict)

    def _format_builtin(self, analysis: IssueAnalysis) -> str:
        """
        Format using built-in Python methods.

        Args:
            analysis: IssueAnalysis object

        Returns:
            Formatted markdown string
        """
        sections = []

        # 1. Requirements Breakdown
        if analysis.functional_requirements or analysis.non_functional_requirements:
            sections.extend(self._format_requirements(analysis))

        # 2. Acceptance Criteria
        if analysis.acceptance_criteria:
            sections.extend(self._format_acceptance_criteria(analysis))

        # 3. Technical Approach
        if analysis.technical_approach:
            sections.extend(self._format_technical_approach(analysis))

        # 4. Dependencies
        if analysis.dependencies:
            sections.extend(self._format_dependencies(analysis))

        # 5. Potential Risks
        if analysis.risks:
            sections.extend(self._format_risks(analysis))

        # 6. Edge Cases
        if analysis.edge_cases:
            sections.extend(self._format_edge_cases(analysis))

        # 7. Suggested Subtasks
        if analysis.suggested_subtasks:
            sections.extend(self._format_subtasks(analysis))

        # 8. Complexity & Effort
        if analysis.complexity_score or analysis.estimated_effort:
            sections.extend(self._format_complexity(analysis))

        return "\n".join(sections)

    def _format_requirements(self, analysis: IssueAnalysis) -> List[str]:
        """Format requirements section."""
        sections = ["## 1. Requirements Breakdown"]

        if analysis.functional_requirements:
            sections.append("\n**Functional Requirements:**")
            for req in analysis.functional_requirements:
                sections.append(f"- {req}")

        if analysis.non_functional_requirements:
            sections.append("\n**Non-Functional Requirements:**")
            for req in analysis.non_functional_requirements:
                sections.append(f"- {req}")

        sections.append("")
        return sections

    def _format_acceptance_criteria(self, analysis: IssueAnalysis) -> List[str]:
        """Format acceptance criteria section."""
        sections = ["## 2. Acceptance Criteria"]

        for criterion in analysis.acceptance_criteria:
            sections.append(f"- [ ] {criterion}")

        sections.append("")
        return sections

    def _format_technical_approach(self, analysis: IssueAnalysis) -> List[str]:
        """Format technical approach section."""
        sections = [
            "## 3. Technical Approach",
            analysis.technical_approach,
            ""
        ]
        return sections

    def _format_dependencies(self, analysis: IssueAnalysis) -> List[str]:
        """Format dependencies section."""
        sections = ["## 4. Dependencies"]

        for dep in analysis.dependencies:
            sections.append(f"- {dep}")

        sections.append("")
        return sections

    def _format_risks(self, analysis: IssueAnalysis) -> List[str]:
        """Format risks section."""
        sections = ["## 5. Potential Risks"]

        for risk in analysis.risks:
            sections.append(f"- ⚠️ {risk}")

        sections.append("")
        return sections

    def _format_edge_cases(self, analysis: IssueAnalysis) -> List[str]:
        """Format edge cases section."""
        sections = ["## 6. Edge Cases to Consider"]

        for edge_case in analysis.edge_cases:
            sections.append(f"- {edge_case}")

        sections.append("")
        return sections

    def _format_subtasks(self, analysis: IssueAnalysis) -> List[str]:
        """Format subtasks section."""
        sections = ["## 7. Suggested Subtasks"]

        for i, subtask in enumerate(analysis.suggested_subtasks, 1):
            sections.append(f"\n**{i}. {subtask.get('summary', 'Subtask')}**")
            sections.append(f"{subtask.get('description', '')}")

        sections.append("")
        return sections

    def _format_complexity(self, analysis: IssueAnalysis) -> List[str]:
        """Format complexity assessment section."""
        sections = ["## 8. Complexity Assessment"]

        if analysis.complexity_score:
            sections.append(f"**Complexity:** {analysis.complexity_score.title()}")

        if analysis.estimated_effort:
            sections.append(f"**Estimated Effort:** {analysis.estimated_effort}")

        sections.append("")
        return sections
