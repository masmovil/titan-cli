"""
Template constants for AI prompts and issue formatting.
"""

AI_PROMPT_TEMPLATE = """You are an assistant that helps create well-structured Jira issues.

**Issue Type:** {issue_type}
**User's brief description:**
{brief_description}

Your task is to generate:
1. A **concise title** (max 60 characters, clear and descriptive)
2. A **detailed description** with the following sections:
   - Expanded description (2-3 clear paragraphs)
   - Objective (1-2 sentences about what we want to achieve)
   - Acceptance Criteria (checkbox list, minimum 3, specific and testable)
   - Gherkin Tests (test scenarios in Given-When-Then format)
   - Technical Notes (optional, if applicable)
   - Dependencies (optional, if depends on other tasks/services)

Generate in this exact format:

TITLE:
[concise title here]

DESCRIPTION:
[expanded description in 2-3 paragraphs, NO numbering]

OBJECTIVE:
[objective in 1-2 sentences, NO numbering]

ACCEPTANCE_CRITERIA:
- [ ] Specific criterion 1
- [ ] Specific criterion 2
- [ ] Specific criterion 3

GHERKIN_TESTS:
Scenario: [scenario name]
  Given [initial context]
  When [user action]
  Then [expected result]

TECHNICAL_NOTES:
[technical notes or "N/A"]

DEPENDENCIES:
[dependencies or "N/A"]

IMPORTANT:
- Title must be brief (max 60 chars) and descriptive
- DO NOT number sections (no "1.", "2.", etc.)
- Be concise, specific, and professional
- Use technical but clear tone
- Acceptance criteria must be verifiable
- Gherkin tests should cover main cases
"""

JIRA_PLAN_PROMPT_TEMPLATE = """You are being launched from Titan CLI to help plan work for a JIRA issue.

Start as you normally would: load and follow this project's own documentation and any
skills/onboarding material it points to (e.g. CLAUDE.md, README, harness docs) before
looking at the issue below.

Here is the full context of the JIRA issue, including all comments:

{context}

Your task right now is PLANNING ONLY:
1. Study the issue and its comments above.
2. Explore only the specific, necessary parts of the codebase directly related to this
   issue to understand what changes are required. Do not do a broad or exhaustive
   exploration of the whole project - stay narrowly scoped to avoid wasting effort on
   anything not relevant to this issue.
3. Break the work down into a clear, ordered list of concrete steps.
4. Present that plan to the user and explicitly ask them to confirm or adjust it before
   doing any further work.

Do not start implementing until the user has confirmed the plan. When you exit this
session, control returns to Titan CLI and this workflow ends.
"""

FALLBACK_ISSUE_TEMPLATE = """## Description

{{ description }}

## Objective

{{ objective }}

## Acceptance Criteria

{{ acceptance_criteria }}
"""
