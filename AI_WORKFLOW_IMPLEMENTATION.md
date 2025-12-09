# AI-Powered PR Workflow Implementation

## 📋 Overview

This document describes the fully automated AI-powered PR creation workflow in Titan CLI. This workflow provides a completely hands-free experience for creating Pull Requests with AI assistance.

## 🎯 Goals

1. **Atomic Commits**: AI automatically analyzes changes and creates atomic commits grouped by logical units
2. **Branch Analysis**: AI analyzes the complete branch diff (not just staged changes)
3. **Template-Based PR**: AI generates PR description following the project's PR template
4. **Opt-In by Default**: AI features are opt-in, keeping deterministic behavior as default

## 🏗️ Architecture

### Workflow Files

#### 1. **create-pr.yaml** (Manual/Deterministic)
- Default workflow for creating PRs
- `use_ai: false` by default
- Prompts user for commit message and PR details
- AI step is optional and skipped by default

#### 2. **create-pr-ai.yaml** (Fully Automated)
- AI-powered workflow for automatic PR creation
- `use_ai: true` always enabled
- Automatically creates atomic commits
- Analyzes full branch diff for PR generation
- Uses PR template for structured output

### Step Implementations

#### 1. **ai_atomic_commits_step.py**

**Purpose**: Automatically create atomic commits using AI analysis

**Flow**:
```
1. Analyze all modified/untracked files
2. Get diffs for each file
3. AI groups changes by logical units:
   - Features
   - Bug fixes
   - Refactors
   - Documentation
   - Tests
4. Create separate commits for each group
5. Use conventional commits format
```

**AI Prompt**:
- Receives: File list + diffs
- Returns: List of commits with files and messages
- Format:
  ```
  COMMIT 1:
  FILES: file1.py, file2.py
  MESSAGE: feat(auth): add user authentication
  ```

**User Interaction**:
- Shows proposed commits to user
- User confirms before creating
- Falls back to manual commit if declined

#### 2. **ai_pr_step.py** (Enhanced)

**Purpose**: Generate PR title and body using full branch analysis

**Flow**:
```
1. Get current branch and base branch
2. Fetch all commits in branch
3. Get complete branch diff (base...head)
4. Read PR template (.github/pull_request_template.md)
5. AI analyzes diff + commits + template
6. Generate PR title (conventional commits)
7. Generate PR body (following template)
```

**AI Prompt Structure**:
```markdown
## Branch Information
- Current branch: feat/new-feature
- Base branch: main
- Files changed: 15
- Total commits: 3

## Commits in Branch
- feat: add authentication
- test: add auth tests
- docs: update README

## Changed Files
- src/auth/oauth.py
- src/auth/tokens.py
- tests/test_auth.py
...

## Branch Diff Preview
```diff
[Full diff limited to 8000 chars]
```

## PR Template to Follow
[Content of .github/pull_request_template.md]

## Instructions
Generate PR following template with:
- Title: type(scope): description (max 72 chars)
- Body: Fill all template sections
- Checkboxes: Mark with [x] where applicable
```

**Response Format**:
```
TITLE: feat(auth): add OAuth2 authentication system

DESCRIPTION:
# Pull Request

## 📝 Summary
This PR implements OAuth2 authentication...

## 🎯 Type of Change
- [x] ✨ New feature
- [ ] 🐛 Bug fix
...
```

### PR Template

Located at: `.github/pull_request_template.md`

**Sections**:
- 📝 Summary
- 🎯 Type of Change (checkboxes)
- 🔧 Changes Made (bullet list)
- 🧪 Testing (how tested + checklist)
- 📸 Screenshots (if UI changes)
- ✅ Checklist (code quality checks)
- 🔗 Related Issues
- 📎 Additional Context

## 🔄 Workflow Comparison

### Manual Workflow (create-pr)

```yaml
steps:
  1. Check git status
  2. Prompt for commit message ← User input required
  3. Create commit
  4. Push to remote
  5. Get branches
  6. [SKIP] AI suggest PR (use_ai=false)
  7. Prompt for PR title ← User input required
  8. Prompt for PR body ← User input required
  9. Create PR
```

### AI Workflow (create-pr-ai)

```yaml
steps:
  1. Check git status
  2. AI create atomic commits ← Fully automated
     - Analyze changes
     - Group by logical units
     - Create multiple commits
     [Fallback to manual if fails]
  3. Push to remote
  4. Get branches
  5. AI generate PR description ← Fully automated
     - Analyze branch diff
     - Read commits
     - Follow template
  6. Create PR
```

## 🎮 User Experience

### Menu Option: "Create PR with AI"

**Before Execution**:
```
⚠️  You have uncommitted changes.

This workflow will:
  1. AI analyzes your changes and creates atomic commits
  2. Push commits to remote
  3. AI analyzes branch diff and generates PR description
  4. Create Pull Request automatically

Continue? [Y/n]
```

### Atomic Commits Phase

```
📝 Analyzing 15 changed files...

🤖 AI is analyzing changes to create atomic commits...

📦 AI Proposed 3 Atomic Commits:

  1. feat(auth): add OAuth2 authentication system
     Files: src/auth/oauth.py, src/auth/tokens.py (+2 more)

  2. test(auth): add comprehensive auth tests
     Files: tests/test_auth.py

  3. docs: update README with authentication setup
     Files: README.md, docs/AUTH.md

Create these atomic commits? [Y/n]
```

### PR Generation Phase

```
📊 Analyzing branch diff: feat/oauth vs main...

🤖 Generating PR description with AI...

📝 AI Generated PR:
  Title: feat(auth): add OAuth2 authentication system

╭─ Description ─────────────────────────────╮
│ # Pull Request                            │
│                                           │
│ ## 📝 Summary                             │
│ This PR implements OAuth2 authentication  │
│ system supporting Google and GitHub...    │
│                                           │
│ ## 🎯 Type of Change                      │
│ - [x] ✨ New feature                      │
│ ...                                       │
╰───────────────────────────────────────────╯

Use this AI-generated PR description? [Y/n]
```

## 🔧 Implementation Details

### Git Client Methods Required

The AI workflow requires these methods in the Git client:

```python
# Get commits in branch
git_client.get_branch_commits(base_branch, current_branch) -> List[str]

# Get full branch diff
git_client.get_branch_diff(base_branch, current_branch) -> str

# Get file diff
git_client.get_file_diff(file_path) -> str

# Stage file
git_client.stage_file(file_path) -> None

# Create commit
git_client.commit(message) -> bool
```

### PlatformAgent Integration

The AI steps use PlatformAgent for analysis:

```python
from titan_cli.agents import PlatformAgent

agent = PlatformAgent.from_toml("config/agents/platform_agent.toml")

result = agent.run(
    ctx=ctx,
    user_context=prompt,
    mode="analysis"  # Non-interactive mode
)
```

### Error Handling

**Graceful Degradation**:
- If AI step fails → Skip and fallback to manual prompts
- If atomic commits fail → Prompt for single commit message
- If PR generation fails → Prompt for title and body

**Error Messages**:
```python
Skip("AI not configured. Run 'titan ai configure'")
Skip("AI not requested (use_ai=false)")
Skip("PlatformAgent config not found")
Error("Git client not available")
```

## 📊 Token Management

To avoid token overflow, the implementation limits:

- **File diffs**: First 10 files when no branch diff available
- **Commits**: First 15 commits shown
- **Changed files**: First 30 files listed
- **Branch diff**: Truncated at 8000 chars

## ✅ Testing

### Test Files

1. **test_opt_in_behavior.py**
   - Verifies AI is opt-in by default
   - Tests `use_ai=false` (skip)
   - Tests `use_ai=true` (execute)
   - Tests AI not configured (skip)

2. **test_workflow_execution.py**
   - Tests AI workflow with enabled AI
   - Tests AI workflow with disabled AI

### Manual Testing

```bash
# Test AI workflow
poetry run titan

# Select: "Create PR with AI"

# Verify:
✓ Atomic commits created
✓ PR template followed
✓ Conventional commit format
✓ All checkboxes present
```

## 📝 Configuration

### Enable AI

```bash
titan ai configure

# Select provider (Anthropic, OpenAI, Gemini)
# Enter API key
```

### Verify AI

```bash
# From menu: "Test AI Connection"
# Or manually check:
cat ~/.config/titan/config.toml
```

Should show:
```toml
[ai]
provider = "anthropic"
model = "claude-3-5-sonnet-20241022"
```

## 🎯 Benefits

1. **Time Savings**: No manual commit message writing or PR description drafting
2. **Consistency**: All PRs follow template structure
3. **Quality**: Atomic commits improve git history
4. **Standards**: Conventional commits enforced
5. **Context**: AI analyzes full branch, not just staged changes

## 🔮 Future Enhancements

1. **Smart Commit Grouping**: ML-based file relationship analysis
2. **PR Size Warnings**: Suggest splitting large PRs
3. **Auto-Reviewers**: Suggest reviewers based on changed files
4. **Auto-Labels**: Add labels based on PR type
5. **Changelog Generation**: Auto-update CHANGELOG.md
6. **Breaking Change Detection**: Warn about breaking changes

## 📚 Documentation Links

- [AI Opt-In Summary](./AI_OPT_IN_SUMMARY.md)
- [Menu Implementation](./MENU_AI_PR_IMPLEMENTATION.md)
- [PlatformAgent Integration](./PLATFORM_AGENT_INTEGRATION_PLAN.md)
- [Agent Steps Guide](./docs/AGENT_STEPS.md)

---

**Implementation Status**: ✅ Complete
**Version**: 1.0
**Last Updated**: 2025-12-09
