# plugins/titan-plugin-jira/titan_plugin_jira/agents/jira_agent.py
"""
JiraAgent - Intelligent orchestrator for JIRA workflows.

This agent analyzes JIRA issues and automatically:
1. Extracts technical requirements from descriptions
2. Generates enhanced descriptions with structured format
3. Suggests subtasks for complex issues
4. Generates helpful comments with technical insights
5. Identifies risks and dependencies
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from titan_cli.ai.agents.base import BaseAIAgent, AgentRequest
from .config_loader import load_agent_config

# Set up logger
logger = logging.getLogger(__name__)


@dataclass
class IssueAnalysis:
    """Complete analysis result from JiraAgent."""

    # Requirements analysis
    functional_requirements: List[str] = field(default_factory=list)
    non_functional_requirements: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)

    # Technical analysis
    technical_approach: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    edge_cases: List[str] = field(default_factory=list)

    # Suggested content
    enhanced_description: Optional[str] = None
    suggested_subtasks: List[Dict[str, str]] = field(default_factory=list)
    suggested_comments: List[str] = field(default_factory=list)

    # Metadata
    total_tokens_used: int = 0
    complexity_score: Optional[str] = None  # "low", "medium", "high", "very high"
    estimated_effort: Optional[str] = None  # "1-2 days", "3-5 days", "1-2 weeks", etc.


class JiraAgent(BaseAIAgent):
    """
    AI agent for intelligent JIRA issue analysis and requirements generation.

    This agent:
    - Analyzes issue descriptions and extracts structured requirements
    - Enhances descriptions with proper formatting and clarity
    - Suggests subtasks for complex work breakdown
    - Generates helpful technical comments
    - Identifies risks, dependencies, and edge cases

    Example:
        ```python
        # In a workflow step
        jira_agent = JiraAgent(ctx.ai, ctx.jira)

        # Analyze an issue
        analysis = jira_agent.analyze_issue(
            issue_key="PROJ-123",
            include_subtasks=True,
            include_comments=True
        )

        # Use the analysis
        if analysis.suggested_subtasks:
            for subtask in analysis.suggested_subtasks:
                # Create subtasks in JIRA
                pass
        ```
    """

    def __init__(self, ai_client, jira_client=None):
        """
        Initialize JiraAgent.

        Args:
            ai_client: The AIClient instance (provides AI capabilities)
            jira_client: Optional JIRA client for issue operations
        """
        super().__init__(ai_client)
        self.jira = jira_client

        # Load configuration from TOML (once per agent instance)
        self.config = load_agent_config("jira_agent")

    def get_system_prompt(self) -> str:
        """System prompt for requirements analysis (from config)."""
        return self.config.requirements_system_prompt

    def analyze_issue(
        self,
        issue_key: str,
        include_subtasks: bool = True,
        include_comments: bool = False,
        include_linked_issues: bool = False
    ) -> IssueAnalysis:
        """
        Analyze a JIRA issue and extract requirements, risks, and suggestions.

        Args:
            issue_key: The JIRA issue key (e.g., "PROJ-123")
            include_subtasks: Whether to suggest subtasks
            include_comments: Whether to analyze existing comments
            include_linked_issues: Whether to consider linked issues

        Returns:
            IssueAnalysis with complete analysis (gracefully handles errors)
        """
        if not self.jira:
            logger.error("JiraClient not available for issue analysis")
            return IssueAnalysis()

        total_tokens = 0

        # Initialize with safe defaults
        functional_reqs = []
        non_functional_reqs = []
        acceptance_criteria = []
        technical_approach = None
        dependencies = []
        risks = []
        edge_cases = []
        enhanced_description = None
        suggested_subtasks = []
        suggested_comments = []
        complexity_score = None
        estimated_effort = None

        # 1. Get issue from JIRA (with error handling)
        try:
            issue = self.jira.get_ticket(issue_key)

            # 2. Analyze requirements (with AI error handling)
            if self.config.enable_requirement_extraction:
                try:
                    requirements_result = self._extract_requirements(issue)
                    functional_reqs = requirements_result.get("functional", [])
                    non_functional_reqs = requirements_result.get("non_functional", [])
                    acceptance_criteria = requirements_result.get("acceptance_criteria", [])
                    technical_approach = requirements_result.get("technical_approach")
                    total_tokens += requirements_result.get("tokens_used", 0)
                except Exception as e:
                    logger.warning(f"Failed to extract requirements: {e}")

            # 3. Analyze risks and dependencies (with AI error handling)
            if self.config.enable_risk_analysis:
                try:
                    risk_result = self._analyze_risks(issue)
                    risks = risk_result.get("risks", [])
                    edge_cases = risk_result.get("edge_cases", [])
                    complexity_score = risk_result.get("complexity")
                    estimated_effort = risk_result.get("effort")
                    total_tokens += risk_result.get("tokens_used", 0)
                except Exception as e:
                    logger.warning(f"Failed to analyze risks: {e}")

            # 4. Detect dependencies (with AI error handling)
            if self.config.enable_dependency_detection:
                try:
                    dep_result = self._detect_dependencies(issue)
                    dependencies = dep_result.get("dependencies", [])
                    total_tokens += dep_result.get("tokens_used", 0)
                except Exception as e:
                    logger.warning(f"Failed to detect dependencies: {e}")

            # 5. Suggest subtasks (with AI error handling)
            if include_subtasks and self.config.enable_subtask_suggestion:
                try:
                    subtask_result = self._suggest_subtasks(issue)
                    suggested_subtasks = subtask_result.get("subtasks", [])
                    total_tokens += subtask_result.get("tokens_used", 0)
                except Exception as e:
                    logger.warning(f"Failed to suggest subtasks: {e}")

        except Exception as e:
            logger.error(f"Failed to get issue {issue_key}: {e}")
            # Return empty analysis on complete failure

        return IssueAnalysis(
            functional_requirements=functional_reqs,
            non_functional_requirements=non_functional_reqs,
            acceptance_criteria=acceptance_criteria,
            technical_approach=technical_approach,
            dependencies=dependencies,
            risks=risks,
            edge_cases=edge_cases,
            enhanced_description=enhanced_description,
            suggested_subtasks=suggested_subtasks,
            suggested_comments=suggested_comments,
            total_tokens_used=total_tokens,
            complexity_score=complexity_score,
            estimated_effort=estimated_effort
        )

    def _extract_requirements(self, issue) -> Dict[str, Any]:
        """
        Extract functional and non-functional requirements from issue.

        Args:
            issue: JiraTicket object

        Returns:
            Dict with keys: functional, non_functional, acceptance_criteria,
                           technical_approach, tokens_used

        Raises:
            ValueError: If issue description is empty
            Exception: If AI generation fails
        """
        description = issue.description or ""
        if not description.strip():
            raise ValueError("Cannot extract requirements from empty description")

        # Truncate description if too large
        max_length = self.config.max_description_length
        desc_preview = description[:max_length]
        if len(description) > max_length:
            desc_preview += "\n\n... (description truncated)"

        prompt = f"""Analyze this JIRA issue and extract technical requirements.

Issue: {issue.key} - {issue.summary}
Type: {issue.issue_type}
Priority: {issue.priority}

Description:
{desc_preview}

Extract and categorize requirements. Format your response EXACTLY like this:

FUNCTIONAL_REQUIREMENTS:
- <requirement 1>
- <requirement 2>

NON_FUNCTIONAL_REQUIREMENTS:
- <requirement 1>
- <requirement 2>

ACCEPTANCE_CRITERIA:
- <criterion 1>
- <criterion 2>

TECHNICAL_APPROACH:
<brief technical approach suggestion>"""

        request = AgentRequest(
            context=prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system_prompt=self.config.requirements_system_prompt
        )

        try:
            response = self.generate(request)
        except Exception as e:
            logger.error(f"AI generation failed for requirements extraction: {e}")
            raise

        # Debug: Log AI response if debug enabled
        if self.config.enable_debug_output:
            logger.info("=" * 80)
            logger.info("AI RESPONSE FOR REQUIREMENTS EXTRACTION:")
            logger.info(response.content)
            logger.info("=" * 80)

        # Parse response
        result = self._parse_requirements_response(response.content)

        # Debug: Log parsing result if debug enabled
        if self.config.enable_debug_output:
            logger.info("PARSED RESULT:")
            logger.info(f"  Functional: {len(result.get('functional', []))} items")
            logger.info(f"  Non-functional: {len(result.get('non_functional', []))} items")
            logger.info(f"  Acceptance criteria: {len(result.get('acceptance_criteria', []))} items")
            logger.info(f"  Technical approach: {result.get('technical_approach') is not None}")

        result["tokens_used"] = response.tokens_used

        return result

    def _analyze_risks(self, issue) -> Dict[str, Any]:
        """
        Analyze risks and edge cases for the issue.

        Args:
            issue: JiraTicket object

        Returns:
            Dict with keys: risks, edge_cases, complexity, effort, tokens_used
        """
        description = issue.description or ""
        desc_preview = description[:self.config.max_description_length]

        prompt = f"""Analyze this JIRA issue for risks and complexity.

Issue: {issue.key} - {issue.summary}
Type: {issue.issue_type}
Priority: {issue.priority}

Description:
{desc_preview}

Identify potential risks, edge cases, and estimate complexity. Format your response EXACTLY like this:

RISKS:
- <risk 1>
- <risk 2>

EDGE_CASES:
- <edge case 1>
- <edge case 2>

COMPLEXITY: <low|medium|high|very high>
EFFORT_ESTIMATE: <1-2 days|3-5 days|1-2 weeks|2+ weeks>"""

        request = AgentRequest(
            context=prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system_prompt=self.config.requirements_system_prompt
        )

        try:
            response = self.generate(request)
            result = self._parse_risk_response(response.content)
            result["tokens_used"] = response.tokens_used
            return result
        except Exception as e:
            logger.error(f"AI generation failed for risk analysis: {e}")
            raise

    def _detect_dependencies(self, issue) -> Dict[str, Any]:
        """
        Detect technical dependencies from issue description.

        Args:
            issue: JiraTicket object

        Returns:
            Dict with keys: dependencies, tokens_used
        """
        description = issue.description or ""
        desc_preview = description[:self.config.max_description_length]

        prompt = f"""Analyze this JIRA issue and identify technical dependencies.

Issue: {issue.key} - {issue.summary}
Type: {issue.issue_type}

Description:
{desc_preview}

Identify external dependencies (APIs, libraries, services, other systems, etc.).
Format your response EXACTLY like this:

DEPENDENCIES:
- <dependency 1>
- <dependency 2>"""

        request = AgentRequest(
            context=prompt,
            max_tokens=self.config.max_tokens // 4,  # Smaller request
            temperature=self.config.temperature,
            system_prompt=self.config.requirements_system_prompt
        )

        try:
            response = self.generate(request)
            result = self._parse_dependencies_response(response.content)
            result["tokens_used"] = response.tokens_used
            return result
        except Exception as e:
            logger.error(f"AI generation failed for dependency detection: {e}")
            raise

    def _suggest_subtasks(self, issue) -> Dict[str, Any]:
        """
        Suggest subtasks for breaking down the issue.

        Args:
            issue: JiraTicket object

        Returns:
            Dict with keys: subtasks (list of dicts with summary and description), tokens_used
        """
        description = issue.description or ""
        desc_preview = description[:self.config.max_description_length]

        prompt = f"""Analyze this JIRA issue and suggest subtasks for work breakdown.

Issue: {issue.key} - {issue.summary}
Type: {issue.issue_type}
Priority: {issue.priority}

Description:
{desc_preview}

Suggest up to {self.config.max_subtasks} subtasks. Format your response EXACTLY like this:

SUBTASK_1:
Summary: <concise summary>
Description: <brief technical description>

SUBTASK_2:
Summary: <concise summary>
Description: <brief technical description>"""

        request = AgentRequest(
            context=prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system_prompt=self.config.subtask_suggestion_prompt
        )

        try:
            response = self.generate(request)
            result = self._parse_subtasks_response(response.content)
            result["tokens_used"] = response.tokens_used
            return result
        except Exception as e:
            logger.error(f"AI generation failed for subtask suggestion: {e}")
            raise

    def generate_comment(self, issue_key: str, comment_context: str) -> Optional[str]:
        """
        Generate a helpful comment for a JIRA issue.

        Args:
            issue_key: The JIRA issue key
            comment_context: Context for the comment (e.g., "provide implementation guidance")

        Returns:
            Generated comment text or None on failure
        """
        if not self.jira:
            logger.error("JiraClient not available")
            return None

        try:
            issue = self.jira.get_ticket(issue_key)
            description = issue.description or ""
            desc_preview = description[:self.config.max_description_length]

            prompt = f"""Generate a helpful comment for this JIRA issue.

Issue: {issue.key} - {issue.summary}
Type: {issue.issue_type}
Status: {issue.status}

Description:
{desc_preview}

Context: {comment_context}

Generate a professional, helpful comment. Be specific and actionable.
Format your response EXACTLY like this:

COMMENT:
<comment text>"""

            request = AgentRequest(
                context=prompt,
                max_tokens=self.config.max_tokens // 2,
            temperature=self.config.temperature,
                system_prompt=self.config.comment_generation_prompt
            )

            response = self.generate(request)

            # Extract comment
            if "COMMENT:" in response.content:
                comment = response.content.split("COMMENT:", 1)[1].strip()
                return comment

            return None

        except Exception as e:
            logger.error(f"Failed to generate comment: {e}")
            return None

    # ==================== RESPONSE PARSING METHODS ====================

    def _parse_requirements_response(self, content: str) -> Dict[str, Any]:
        """Parse requirements extraction response."""
        result = {
            "functional": [],
            "non_functional": [],
            "acceptance_criteria": [],
            "technical_approach": None
        }

        sections = {
            "FUNCTIONAL_REQUIREMENTS:": "functional",
            "NON_FUNCTIONAL_REQUIREMENTS:": "non_functional",
            "ACCEPTANCE_CRITERIA:": "acceptance_criteria",
            "TECHNICAL_APPROACH:": "technical_approach"
        }

        current_section = None
        lines = content.split("\n")

        for line in lines:
            line = line.strip()

            # Check for section headers
            for header, section_key in sections.items():
                if line.startswith(header):
                    current_section = section_key
                    break

            # Parse content
            if current_section and line.startswith("-"):
                item = line[1:].strip()
                if current_section in ["functional", "non_functional", "acceptance_criteria"]:
                    result[current_section].append(item)
            elif current_section == "technical_approach" and line and not line.endswith(":"):
                if result["technical_approach"]:
                    result["technical_approach"] += " " + line
                else:
                    result["technical_approach"] = line

        return result

    def _parse_risk_response(self, content: str) -> Dict[str, Any]:
        """Parse risk analysis response."""
        result = {
            "risks": [],
            "edge_cases": [],
            "complexity": None,
            "effort": None
        }

        current_section = None
        lines = content.split("\n")

        for line in lines:
            line = line.strip()

            if line.startswith("RISKS:"):
                current_section = "risks"
            elif line.startswith("EDGE_CASES:"):
                current_section = "edge_cases"
            elif line.startswith("COMPLEXITY:"):
                result["complexity"] = line.split(":", 1)[1].strip()
                current_section = None
            elif line.startswith("EFFORT_ESTIMATE:"):
                result["effort"] = line.split(":", 1)[1].strip()
                current_section = None
            elif current_section and line.startswith("-"):
                item = line[1:].strip()
                result[current_section].append(item)

        return result

    def _parse_dependencies_response(self, content: str) -> Dict[str, Any]:
        """Parse dependencies detection response."""
        result = {"dependencies": []}

        lines = content.split("\n")
        in_deps = False

        for line in lines:
            line = line.strip()
            if line.startswith("DEPENDENCIES:"):
                in_deps = True
            elif in_deps and line.startswith("-"):
                item = line[1:].strip()
                result["dependencies"].append(item)

        return result

    def _parse_subtasks_response(self, content: str) -> Dict[str, Any]:
        """Parse subtasks suggestion response."""
        result = {"subtasks": []}

        current_subtask = None
        lines = content.split("\n")

        for line in lines:
            line = line.strip()

            if line.startswith("SUBTASK_"):
                if current_subtask:
                    result["subtasks"].append(current_subtask)
                current_subtask = {"summary": "", "description": ""}
            elif current_subtask:
                if line.startswith("Summary:"):
                    current_subtask["summary"] = line.split(":", 1)[1].strip()
                elif line.startswith("Description:"):
                    current_subtask["description"] = line.split(":", 1)[1].strip()

        # Add last subtask
        if current_subtask:
            result["subtasks"].append(current_subtask)

        return result
