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

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from titan_cli.core.logging import get_logger
from titan_cli.ai.agents.base import BaseAIAgent, AgentRequest
from titan_cli.core.result import ClientSuccess, ClientError
from .config_loader import load_agent_config
from .contracts import (
    COMMENT_CONTRACT,
    DEPENDENCY_CONTRACT,
    REQUIREMENTS_CONTRACT,
    RISK_CONTRACT,
    SUBTASK_CONTRACT,
)
from .validators import IssueValidator
from .token_tracker import TokenTracker, TokenBudget, OperationType
from .prompts import JiraAgentPrompts

# Set up logger
logger = get_logger(__name__)


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

    def __init__(self, generator, jira_client=None):
        """
        Initialize JiraAgent.

        Args:
            generator: Anything implementing AIGenerator - a remote connection
                or a local CLI. This agent works the same either way.
            jira_client: Optional JIRA client for issue operations
        """
        super().__init__(generator)
        self.jira = jira_client

        # Load configuration from TOML (once per agent instance)
        self.config = load_agent_config("jira_agent")

        # Initialize robust response parser

        # Initialize input validator
        self.validator = IssueValidator(
            strict=False,
            min_description_length=10
        )

        # Initialize token tracker with budget
        self.token_budget = TokenBudget(base_max_tokens=self.config.max_tokens)
        self.token_tracker = TokenTracker(self.token_budget)

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

        # Reset token tracker for this analysis
        self.token_tracker.reset()

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
            result = self.jira.get_issue(issue_key)

            # Handle Result
            match result:
                case ClientSuccess(data=issue):
                    pass  # Continue with issue
                case ClientError(error_message=err):
                    logger.error(f"Failed to get issue {issue_key}: {err}")
                    return IssueAnalysis()

            # 2. Analyze requirements (with AI error handling)
            if self.config.enable_requirement_extraction:
                try:
                    requirements_result = self._extract_requirements(issue)
                    functional_reqs = requirements_result.get("functional", [])
                    non_functional_reqs = requirements_result.get("non_functional", [])
                    acceptance_criteria = requirements_result.get("acceptance_criteria", [])
                    technical_approach = requirements_result.get("technical_approach")
                    # Track tokens
                    tokens_used = requirements_result.get("tokens_used", 0)
                    self.token_tracker.record_usage(
                        OperationType.REQUIREMENTS_EXTRACTION,
                        tokens_used,
                        issue_key=issue_key,
                        success=True
                    )
                except Exception as e:
                    logger.warning(f"Failed to extract requirements: {e}")
                    self.token_tracker.record_usage(
                        OperationType.REQUIREMENTS_EXTRACTION,
                        0,
                        issue_key=issue_key,
                        success=False,
                        error=str(e)
                    )

            # 3. Analyze risks and dependencies (with AI error handling)
            if self.config.enable_risk_analysis:
                try:
                    risk_result = self._analyze_risks(issue)
                    risks = risk_result.get("risks", [])
                    edge_cases = risk_result.get("edge_cases", [])
                    complexity_score = risk_result.get("complexity")
                    estimated_effort = risk_result.get("effort")
                    # Track tokens
                    tokens_used = risk_result.get("tokens_used", 0)
                    self.token_tracker.record_usage(
                        OperationType.RISK_ANALYSIS,
                        tokens_used,
                        issue_key=issue_key,
                        success=True
                    )
                except Exception as e:
                    logger.warning(f"Failed to analyze risks: {e}")
                    self.token_tracker.record_usage(
                        OperationType.RISK_ANALYSIS,
                        0,
                        issue_key=issue_key,
                        success=False,
                        error=str(e)
                    )

            # 4. Detect dependencies (with AI error handling)
            if self.config.enable_dependency_detection:
                try:
                    dep_result = self._detect_dependencies(issue)
                    dependencies = dep_result.get("dependencies", [])
                    # Track tokens
                    tokens_used = dep_result.get("tokens_used", 0)
                    self.token_tracker.record_usage(
                        OperationType.DEPENDENCY_DETECTION,
                        tokens_used,
                        issue_key=issue_key,
                        success=True
                    )
                except Exception as e:
                    logger.warning(f"Failed to detect dependencies: {e}")
                    self.token_tracker.record_usage(
                        OperationType.DEPENDENCY_DETECTION,
                        0,
                        issue_key=issue_key,
                        success=False,
                        error=str(e)
                    )

            # 5. Suggest subtasks (with AI error handling)
            if include_subtasks and self.config.enable_subtasks:
                try:
                    subtask_result = self._suggest_subtasks(issue)
                    suggested_subtasks = subtask_result.get("subtasks", [])
                    # Track tokens
                    tokens_used = subtask_result.get("tokens_used", 0)
                    self.token_tracker.record_usage(
                        OperationType.SUBTASK_SUGGESTION,
                        tokens_used,
                        issue_key=issue_key,
                        success=True
                    )
                except Exception as e:
                    logger.warning(f"Failed to suggest subtasks: {e}")
                    self.token_tracker.record_usage(
                        OperationType.SUBTASK_SUGGESTION,
                        0,
                        issue_key=issue_key,
                        success=False,
                        error=str(e)
                    )

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
            total_tokens_used=self.token_tracker.get_total_tokens(),
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
            ValueError: If issue validation fails
            Exception: If AI generation fails
        """
        # Validate issue data before processing
        is_valid, errors = self.validator.validate_for_requirements_extraction(issue)

        if not is_valid:
            error_msg = f"Issue validation failed for {issue.key}:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ValueError(error_msg)

        # Sanitize and truncate description
        description = issue.description or ""
        max_length = self.config.max_description_length
        desc_preview = self.validator.sanitize_description(description, max_length)

        # Use centralized prompt template
        prompt = JiraAgentPrompts.requirements_extraction(
            issue_key=issue.key,
            summary=issue.summary,
            issue_type=issue.issue_type,
            priority=issue.priority,
            description=desc_preview
        )

        request = AgentRequest(
            context=prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system_prompt=self.config.requirements_system_prompt,
            operation="requirements_extraction",
            contract=REQUIREMENTS_CONTRACT,
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
        result = dict(response.parsed)

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
        desc_preview = self.validator.sanitize_description(
            description,
            self.config.max_description_length
        )

        # Use centralized prompt template
        prompt = JiraAgentPrompts.risk_analysis(
            issue_key=issue.key,
            summary=issue.summary,
            issue_type=issue.issue_type,
            priority=issue.priority,
            description=desc_preview
        )

        request = AgentRequest(
            context=prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system_prompt=self.config.requirements_system_prompt,
            operation="risk_analysis",
            contract=RISK_CONTRACT,
        )

        try:
            response = self.generate(request)
            result = dict(response.parsed)
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
        desc_preview = self.validator.sanitize_description(
            description,
            self.config.max_description_length
        )

        # Use centralized prompt template
        prompt = JiraAgentPrompts.dependency_detection(
            issue_key=issue.key,
            summary=issue.summary,
            issue_type=issue.issue_type,
            description=desc_preview
        )

        request = AgentRequest(
            context=prompt,
            max_tokens=self.token_budget.get_budget(OperationType.DEPENDENCY_DETECTION),
            temperature=self.config.temperature,
            system_prompt=self.config.requirements_system_prompt,
            operation="dependency_detection",
            contract=DEPENDENCY_CONTRACT,
        )

        try:
            response = self.generate(request)
            result = dict(response.parsed)
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
        desc_preview = self.validator.sanitize_description(
            description,
            self.config.max_description_length
        )

        # Use centralized prompt template
        prompt = JiraAgentPrompts.subtask_suggestion(
            issue_key=issue.key,
            summary=issue.summary,
            issue_type=issue.issue_type,
            priority=issue.priority,
            description=desc_preview,
            max_subtasks=self.config.max_subtasks
        )

        request = AgentRequest(
            context=prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system_prompt=self.config.subtask_suggestion_prompt,
            operation="subtask_suggestion",
            contract=SUBTASK_CONTRACT,
        )

        try:
            response = self.generate(request)
            return {
                "subtasks": self._valid_subtasks(response.parsed),
                "tokens_used": response.tokens_used,
            }
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
            result = self.jira.get_issue(issue_key)

            # Handle Result
            match result:
                case ClientSuccess(data=issue):
                    pass  # Continue with issue
                case ClientError(error_message=err):
                    logger.error(f"Failed to get issue {issue_key}: {err}")
                    return None

            description = issue.description or ""
            desc_preview = self.validator.sanitize_description(
                description,
                self.config.max_description_length
            )

            # Use centralized prompt template
            prompt = JiraAgentPrompts.comment_generation(
                issue_key=issue.key,
                summary=issue.summary,
                issue_type=issue.issue_type,
                status=issue.status,
                description=desc_preview,
                comment_context=comment_context
            )

            request = AgentRequest(
                context=prompt,
                max_tokens=self.config.max_tokens // 2,
                temperature=self.config.temperature,
                system_prompt=self.config.comment_generation_prompt,
                operation="comment_generation",
                contract=COMMENT_CONTRACT,
            )

            response = self.generate(request)

            # The prompt asks for a "COMMENT:" label, but the comment is the
            # whole answer either way: a model that writes the comment without
            # the label has still done the job, and discarding it - which is
            # what requiring the label used to mean - throws away a good answer
            # over a formatting detail.
            comment = response.parsed
            if "COMMENT:" in comment:
                comment = comment.split("COMMENT:", 1)[1].strip()

            return comment or None

        except Exception as e:
            logger.error(f"Failed to generate comment: {e}")
            return None

    @staticmethod
    def _valid_subtasks(parsed: Dict[str, Any]) -> list:
        """
        Keep only subtasks Jira could actually create.

        A subtask with no summary has no title, so it is dropped rather than
        sent on to fail at creation time.
        """
        return [
            {"summary": item.get("summary", ""), "description": item.get("description", "")}
            for item in parsed.get("subtasks", [])
            if isinstance(item, dict) and item.get("summary")
        ]
