# AI Opt-In Implementation Summary

## Overview
Titan CLI is now **deterministic by default**. AI features are **opt-in only**.

## Implementation

### Default Behavior (Deterministic)
By default, workflows use manual prompts and deterministic steps:

```yaml
# create-pr.yaml
params:
  use_ai: false  # Default - deterministic behavior
```

**Result**: User is prompted manually for PR title and description.

### Opt-In Behavior (AI-Powered)
Users can explicitly enable AI features:

```yaml
# create-pr.yaml
params:
  use_ai: true  # Explicitly opt-in to AI
```

**Result**: AI analyzes changes and suggests PR title/description.

## How It Works

### 1. Workflow Configuration
File: `plugins/titan-plugin-github/titan_plugin_github/workflows/create-pr.yaml`

```yaml
params:
  base_branch: "main"
  draft: false
  use_ai: false  # Set to true to use AI for PR description generation

steps:
  # AI suggests PR title and body (only runs if use_ai=true, deterministic by default)
  - id: ai_suggest_pr
    name: "AI Suggest PR Description"
    plugin: github
    step: ai_suggest_pr_description
    optional: true  # Skips if use_ai=false or AI not configured

  # Manual prompts (always available as fallback)
  - id: prompt_pr_title
    name: "Prompt for PR Title"
    plugin: github
    step: prompt_for_pr_title

  - id: prompt_pr_body
    name: "Prompt for PR Body"
    plugin: github
    step: prompt_for_pr_body
```

### 2. Step Implementation
File: `plugins/titan-plugin-github/titan_plugin_github/steps/ai_pr_step.py`

```python
def ai_suggest_pr_description(ctx: WorkflowContext, **kwargs) -> WorkflowResult:
    # Check if user explicitly opted-in to AI (default is false)
    use_ai = ctx.data.get("use_ai", False)
    if not use_ai:
        return Skip("AI not requested (use_ai=false). Using manual prompts for deterministic behavior.")

    # Check if AI is configured
    if not ctx.ai:
        return Skip("AI not configured. Run 'titan ai configure' to enable AI features.")

    # ... AI logic here ...
```

## Test Results

All 4 opt-in tests passing:

✓ **Test 1**: AI correctly skipped by default (use_ai not set)
✓ **Test 2**: AI correctly skipped when explicitly disabled (use_ai=false)
✓ **Test 3**: AI correctly executed when opted-in (use_ai=true)
✓ **Test 4**: AI correctly skipped when not configured (even with use_ai=true)

## User Experience

### Scenario 1: Default User (No AI)
```bash
$ titan workflow run create-pr
```
**Result**: Manual prompts for PR title and body (100% deterministic)

### Scenario 2: AI-Enabled User
```bash
$ titan workflow run create-pr --param use_ai=true
```
**Result**: AI analyzes changes and suggests PR description, with option to accept or modify

### Scenario 3: AI Requested but Not Configured
```bash
$ titan workflow run create-pr --param use_ai=true
```
**Result**: Gracefully falls back to manual prompts with helpful message:
```
⚠ AI not configured. Run 'titan ai configure' to enable AI features.
→ Using manual prompts...
```

## Benefits

1. **Deterministic by Default**: Titan maintains its predictable, reliable behavior
2. **Explicit Opt-In**: Users consciously choose when to use AI features
3. **Graceful Degradation**: Falls back to manual prompts if AI unavailable
4. **Clear Documentation**: Workflow YAML clearly shows use_ai parameter
5. **No Breaking Changes**: Existing workflows continue to work deterministically

## Related Files

- Workflow: [create-pr.yaml](plugins/titan-plugin-github/titan_plugin_github/workflows/create-pr.yaml)
- Step: [ai_pr_step.py](plugins/titan-plugin-github/titan_plugin_github/steps/ai_pr_step.py)
- Tests: [test_opt_in_behavior.py](test_opt_in_behavior.py)

## Future Considerations

This pattern can be applied to other AI features:
- AI commit message generation
- AI code review
- AI documentation generation

All should follow the same principle: **deterministic by default, AI opt-in**.
