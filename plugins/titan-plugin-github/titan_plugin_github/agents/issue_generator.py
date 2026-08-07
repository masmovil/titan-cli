from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass
from titan_cli.ai.agents.base import BaseAIAgent, AgentRequest, AIGenerator
from titan_cli.ai.agents.contracts import JsonContract, TextContract

# The generated issue, as one object. `body` carries a whole markdown document,
# which is why the answer is an object with a string field rather than markdown
# with headings a parser would have to guess at.
ISSUE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": ["feature", "improvement", "bug", "refactor", "chore", "documentation"],
        },
        "title": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["category", "title", "body"],
}

ISSUE_CONTRACT = JsonContract(
    schema=ISSUE_SCHEMA,
    required=("category", "title", "body"),
    # An issue is worth generating even from a mangled answer: the labelled-text
    # shape is what models produced before the schema existed, and some still do.
    fallback=TextContract(
        sections=("CATEGORY", "TITLE", "DESCRIPTION"),
        keys={"CATEGORY": "category", "TITLE": "title", "DESCRIPTION": "body"},
    ),
)


@dataclass
class IssueSizeEstimation:
    """
    Issue size estimation with token limits.

    Attributes:
        complexity: Size category (simple, moderate, complex, very_complex)
        max_tokens: Maximum tokens for issue description generation
        description_length: Length of user's description
    """
    complexity: str
    max_tokens: int
    description_length: int


class IssueGeneratorAgent(BaseAIAgent):
    def __init__(self, ai_client: AIGenerator, template_dir: Optional[Path] = None):
        super().__init__(ai_client)
        self.template_dir = template_dir or Path(".github/ISSUE_TEMPLATE")
        self.max_tokens = 8192  # Add token limit configuration
        self.categories = {
            "feature": {
                "template": "feature.md",
                "labels": ["feature"],
                "prefix": "feat"
            },
            "improvement": {
                "template": "improvement.md",
                "labels": ["improvement"],
                "prefix": "improve"
            },
            "bug": {
                "template": "bug.md",
                "labels": ["bug"],
                "prefix": "fix"
            },
            "refactor": {
                "template": "refactor.md",
                "labels": ["refactor", "technical-debt"],
                "prefix": "refactor"
            },
            "chore": {
                "template": "chore.md",
                "labels": ["chore", "maintenance"],
                "prefix": "chore"
            },
            "documentation": {
                "template": "documentation.md",
                "labels": ["documentation"],
                "prefix": "docs"
            }
        }

        # Label aliases for mapping to different repository label conventions
        self.label_aliases = {
            "feature": ["feature", "enhancement", "new-feature", "feat"],
            "improvement": ["improvement", "enhancement", "optimization", "perf"],
            "bug": ["bug", "fix", "defect", "error"],
            "refactor": ["refactor", "refactoring", "technical-debt", "tech-debt"],
            "chore": ["chore", "maintenance", "housekeeping"],
            "documentation": ["documentation", "docs", "doc"]
        }

    def get_system_prompt(self) -> str:
        return """You are an expert at creating highly professional, descriptive, and useful GitHub issues.
Your task is to:
1. Analyze the user's description and categorize it
2. Generate an issue title and detailed description following the appropriate template (if available)
3. Ensure the title follows the Conventional Commits specification WITHOUT scope (e.g., "feat: Add user authentication")
4. Use English for all content
5. Prioritize clarity, conciseness, and actionable detail
6. Preserve any code snippets exactly as provided, formatted in markdown code blocks
"""

    def _load_template(self, template_name: str) -> Optional[str]:
        """
        Load a template file from the template directory.
        Returns None if template doesn't exist or can't be read.
        """
        try:
            template_path = self.template_dir / template_name
            if template_path.exists() and template_path.is_file():
                return template_path.read_text(encoding="utf-8")
        except (IOError, FileNotFoundError, PermissionError, OSError):
            pass
        return None

    def _load_all_templates(self) -> Dict[str, Optional[str]]:
        """
        Load all available templates.
        Returns a dict mapping category name to template content.
        """
        templates = {}
        for category, info in self.categories.items():
            template_content = self._load_template(info["template"])
            templates[category] = template_content
        return templates

    def _estimate_issue_complexity(self, description: str) -> IssueSizeEstimation:
        """
        Estimate issue complexity based on description length and content.

        Args:
            description: User's issue description

        Returns:
            IssueSizeEstimation with complexity and token limits
        """
        desc_length = len(description)
        # Count newlines as indicator of detail
        lines = description.count('\n') + 1
        # Count code blocks as indicator of technical complexity
        code_blocks = description.count('```')

        # Determine complexity and set appropriate token limits
        if desc_length < 200 and lines <= 3 and code_blocks == 0:
            # Simple issue: brief request, quick fix
            complexity = "simple"
            max_tokens = 3000  # Increased to ensure complete JSON
        elif desc_length < 500 and lines <= 10:
            # Moderate issue: standard feature or bug with some detail
            complexity = "moderate"
            max_tokens = 4000  # Increased to ensure complete JSON
        elif desc_length < 1000 and lines <= 25:
            # Complex issue: detailed requirements, multiple aspects
            complexity = "complex"
            max_tokens = 6000  # Increased to ensure complete JSON
        else:
            # Very complex: comprehensive spec, architectural changes
            complexity = "very_complex"
            max_tokens = 8000  # Increased to ensure complete JSON

        return IssueSizeEstimation(
            complexity=complexity,
            max_tokens=max_tokens,
            description_length=desc_length
        )

    def _normalize(self, parsed: Dict[str, str]) -> Dict[str, str]:
        """
        Apply this agent's own rules to a parsed answer.

        The shape is already guaranteed by the contract; what is left is domain
        knowledge the contract has no business holding - namely that a category
        this agent has no template for is treated as a feature.
        """
        category = str(parsed.get("category") or "feature").strip().lower()
        if category not in self.categories:
            category = "feature"

        return {
            "category": category,
            "title": str(parsed.get("title") or "New issue").strip(),
            "body": parsed.get("body") or "",
        }

    def _map_labels_to_available(self, category: str, available_labels: Optional[list] = None) -> list:
        """
        Map category labels to available repository labels using aliases.

        Args:
            category: The issue category
            available_labels: List of labels available in the repository (optional)

        Returns:
            List of labels that exist in the repository, or default labels if no filtering
        """
        default_labels = self.categories.get(category, self.categories["feature"])["labels"]

        # If no available_labels provided, return defaults (no filtering)
        if available_labels is None:
            return default_labels

        # Get aliases for this category
        aliases = self.label_aliases.get(category, [])

        # Find matching labels in the repository
        matched_labels = []
        for alias in aliases:
            # Case-insensitive matching
            if alias.lower() in [label.lower() for label in available_labels]:
                # Find the exact case from available_labels
                matched_label = next(label for label in available_labels if label.lower() == alias.lower())
                if matched_label not in matched_labels:
                    matched_labels.append(matched_label)

        # Fallback: if no matches found, return empty list (graceful degradation)
        return matched_labels

    def generate_issue(self, user_description: str, available_labels: Optional[list] = None) -> Dict[str, any]:
        """
        Generate a complete issue with auto-categorization in a single AI call.

        Returns:
            dict with keys: title, body, category, labels, template_used, tokens_used, complexity
        """
        # Estimate issue complexity to determine appropriate token allocation
        estimation = self._estimate_issue_complexity(user_description)

        # Load all available templates
        all_templates = self._load_all_templates()

        # Build prompt that includes all templates and asks AI to categorize + generate
        templates_section = self._format_templates_for_prompt(all_templates)

        prompt = f"""
Analyze the following issue description and:
1. Categorize it into ONE category: feature, improvement, bug, refactor, chore, or documentation
2. Generate a complete GitHub issue following the appropriate template

User description:
---
{user_description}
---

{templates_section}

Instructions:
- Choose the most appropriate category based on the description
- Follow the template structure for that category (if available)
- Remove all HTML comments (<!-- -->)
- Keep only section headers (##) that have meaningful content
- IMPORTANT: Completely omit optional sections (marked with "Optional") if they don't apply or have no meaningful content
- Never include a section header followed by just a language identifier (e.g., "python", "yaml") without actual code
- Fill in meaningful content for each section you include
- Preserve any code snippets exactly as provided in markdown code blocks
- Use the correct conventional commit prefix for the title
- Adjust detail level based on issue complexity ({estimation.complexity}):
  * Simple: Brief, direct descriptions (1-2 sentences per section)
  * Moderate: Standard detail (2-3 sentences per section)
  * Complex: Comprehensive detail with examples
  * Very Complex: Full context, edge cases, and implementation notes
"""

        # Single AI call for categorization + generation with appropriate token limit
        request = AgentRequest(
            context=prompt,
            contract=ISSUE_CONTRACT,
            max_tokens=estimation.max_tokens,
            operation="issue_generation",
        )
        response = self.generate(request)

        issue = self._normalize(response.parsed)
        category, title, body = issue["category"], issue["title"], issue["body"]

        template_used = all_templates.get(category) is not None

        # Map labels to available repository labels (with fallback to empty list)
        labels = self._map_labels_to_available(category, available_labels)

        return {
            "title": title,
            "body": body,
            "category": category,
            "labels": labels,
            "template_used": template_used,
            "tokens_used": response.tokens_used,
            "complexity": estimation.complexity
        }

    def _format_templates_for_prompt(self, templates: Dict[str, Optional[str]]) -> str:
        """
        Format all templates into a string for the AI prompt.
        """
        if not any(templates.values()):
            return "No templates available. Generate structured content based on category best practices."

        formatted = "Available templates:\n\n"
        for category, template_content in templates.items():
            if template_content:
                category_info = self.categories[category]
                formatted += f"### {category.upper()} (prefix: {category_info['prefix']})\n"
                formatted += f"```\n{template_content}\n```\n\n"
            else:
                formatted += f"### {category.upper()} (no template available)\n\n"

        return formatted
