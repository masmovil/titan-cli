# Titan Plugin - JIRA

JIRA integration plugin for Titan CLI with AI-powered issue management.

## Features

- JIRA issue search and management
- AI-powered requirements analysis
- Workflow automation
- Issue creation and tracking
- **JiraAgent**: Intelligent AI agent for issue analysis and requirements extraction

## Installation

This plugin is installed automatically with Titan CLI when configured with JIRA credentials.

## Configuration

Configure in `.titan/config.toml`:

```toml
[plugins.jira]
enabled = true

[plugins.jira.config]
base_url = "https://your-domain.atlassian.net"
email = "your-email@example.com"
default_project = "PROJECT"
```

API token is stored securely in secrets (prompted on first use or configure via `titan configure jira`).

## JiraAgent - AI-Powered Issue Analysis

The JIRA plugin includes **JiraAgent**, an intelligent AI agent that analyzes issues and provides:

### Capabilities

- ✅ **Requirements Extraction**: Functional and non-functional requirements
- ✅ **Acceptance Criteria**: Structured criteria with checkboxes
- ✅ **Technical Approach**: Implementation suggestions
- ✅ **Risk Analysis**: Potential risks and complexity scoring
- ✅ **Dependency Detection**: External dependencies and blockers
- ✅ **Subtask Suggestion**: Work breakdown with complexity estimates
- ✅ **Gherkin Scenarios**: BDD test scenarios (Given/When/Then)
- ✅ **Smart Labeling**: Platform/type classification (iOS, Android, BFF)

### Agent Configuration

Configure the agent in `plugins/titan-plugin-jira/titan_plugin_jira/config/jira_agent.toml`:

```toml
[agent]
name = "JiraAgent"
description = "AI agent for iOS, Android, and BFF issue analysis"
version = "1.0.0"

[agent.limits]
max_description_length = 8000
max_subtasks = 6
max_comments_to_analyze = 8
max_linked_issues = 5
temperature = 0.3              # AI creativity (0.0-2.0): lower = focused
max_tokens = 2000              # Max tokens per request

[agent.features]
enable_requirement_extraction = true
enable_subtasks = true
enable_gherkin_tests = true
enable_strict_labeling = true
enable_token_saving = true

[agent.formatting]
# Optional: Custom Jinja2 template for output formatting
# If not set, uses built-in Python formatter
template = "issue_analysis.md.j2"
```

### System Prompts

The agent uses specialized prompts for iOS/Android/BFF development:

- **Requirements Analysis**: Extracts user stories with API/contract impact
- **Description Enhancement**: Structures issues with Gherkin scenarios
- **Subtask Suggestion**: Breaks down work (Implementation, QA, Documentation)
- **Smart Labeling**: Classifies by platform, type, and priority

### Usage in Workflows

The agent is automatically used in the "Analyze JIRA Issues" workflow:

```yaml
steps:
  - id: analyze_issue
    name: "AI Analyze Issue Requirements"
    plugin: jira
    step: ai_analyze_issue_requirements
```

**Output includes**:
1. Requirements Breakdown (Functional/Non-Functional)
2. Acceptance Criteria (checkbox format)
3. Technical Approach
4. Dependencies
5. Potential Risks (⚠️ highlighted)
6. Edge Cases
7. Suggested Subtasks (with summaries)
8. Complexity Assessment (Low/Medium/High/Very High + Effort estimate)

### Output Formatting

The analysis output can be customized using **Jinja2 templates** with automatic fallback to a built-in Python formatter.

#### Template System

**Default Template**: `config/templates/issue_analysis.md.j2` (included)
- Structured markdown output with 8 sections
- Conditional rendering (only shows sections with data)
- Professional formatting for JIRA issues

**Built-in Fallback**: If template not found or Jinja2 not installed
- Pure Python implementation (no dependencies)
- Same structure and content as template
- Ensures reliability across environments

#### Creating Custom Templates

**1. Create template file** in `config/templates/`:
```bash
plugins/titan-plugin-jira/titan_plugin_jira/config/templates/my_template.md.j2
```

**2. Configure in `jira_agent.toml`**:
```toml
[agent.formatting]
template = "my_template.md.j2"
```

**3. Available template variables** (from `IssueAnalysis` dataclass):
```jinja2
# Lists
{{ functional_requirements }}        # List[str]
{{ non_functional_requirements }}    # List[str]
{{ acceptance_criteria }}            # List[str]
{{ dependencies }}                   # List[str]
{{ risks }}                          # List[str]
{{ edge_cases }}                     # List[str]
{{ suggested_subtasks }}             # List[Dict[str, str]]

# Strings
{{ technical_approach }}             # Optional[str]
{{ enhanced_description }}           # Optional[str]
{{ complexity_score }}               # "low"|"medium"|"high"|"very high"
{{ estimated_effort }}               # e.g., "3-5 days"

# Metadata
{{ total_tokens_used }}              # int
```

**4. Example custom template**:
```jinja2
# JIRA Issue Analysis

{% if functional_requirements %}
## Functional Requirements
{% for req in functional_requirements %}
- ✓ {{ req }}
{% endfor %}
{% endif %}

{% if risks %}
## ⚠️ Risks
{% for risk in risks %}
- {{ risk }}
{% endfor %}
{% endif %}

{% if complexity_score %}
**Complexity**: {{ complexity_score|upper }}
{% endif %}
```

**Template Tips**:
- Use `{% if variable %}` for conditional sections
- Use `{{ variable|title }}` for filters (title, upper, lower, etc.)
- Access dict fields: `{{ subtask.summary }}`, `{{ subtask.description }}`
- Keep templates in sync with `IssueAnalysis` dataclass structure

### Available Workflows

- **Analyze JIRA Issues** - Search and analyze issues with AI

## Available Steps

The JIRA plugin provides reusable workflow steps:

### `search_saved_query`
Search JIRA using saved queries (filters).

**Inputs:**
- `query_name` (string, optional): Saved query name

### `prompt_select_issue`
Interactive issue selection prompt.

**Outputs:**
- `selected_issue` (JiraTicket): Selected issue object

### `get_issue`
Get a specific JIRA issue by key.

**Inputs:**
- `issue_key` (string): JIRA issue key (e.g., "PROJ-123")

**Outputs:**
- `jira_issue` (JiraTicket): Issue object

### `ai_analyze_issue_requirements`
AI-powered issue analysis using JiraAgent.

**Inputs:**
- `jira_issue` (JiraTicket): Issue to analyze

**Outputs:**
- `ai_analysis` (string): Formatted markdown analysis
- `ai_analysis_structured` (dict): Structured analysis data
- `tokens_used` (int): AI tokens consumed
- `complexity` (string): Complexity score
- `effort` (string): Effort estimate

## Development

Run tests:
```bash
cd plugins/titan-plugin-jira
poetry run pytest
```

## Troubleshooting

### Missing API Token

**Error:**
```
❌ JIRA API token not found in secrets
```

**Solution:**
```bash
titan configure jira
# Enter your JIRA API token when prompted
```

### Invalid Credentials

**Error:**
```
❌ JIRA API error: 401 Unauthorized
```

**Solution:**
Verify your credentials in `.titan/config.toml` and regenerate your API token:
- JIRA Cloud: https://id.atlassian.com/manage/api-tokens
- JIRA Server: Use Personal Access Token

### Agent Not Working

**Error:**
```
ℹ️  AI not configured - skipping analysis
```

**Solution:**
Configure AI provider:
```bash
titan configure ai
# Select Anthropic or Gemini and provide API key
```

## Related Documentation

- [JIRA REST API Documentation](https://developer.atlassian.com/server/jira/platform/rest-apis/)
- [Titan CLI Documentation](../../README.md)
- [AI Agent Architecture](../../titan_cli/ai/agents/README.md)
