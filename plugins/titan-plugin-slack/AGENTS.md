# AGENTS.md - Titan Slack Plugin

Documentation for AI coding agents working on the `titan-plugin-slack`.

---

## Plugin Overview

**Titan Slack Plugin** provides Slack integration for Titan CLI.

Current first-phase scope:

- Official Titan plugin package and discovery entry point
- Personal user-token Slack client baseline
- Keyring-first secret policy
- BYO Slack App + PKCE connection flow
- No workflow steps yet
- No built-in workflows yet

---

## Project Structure

```text
titan_plugin_slack/
├── __init__.py
├── plugin.py
├── clients/
│   └── slack_client.py
├── screens/
│   └── slack_config_screen.py
├── models.py
├── exceptions.py
├── oauth.py
├── steps/
└── workflows/
```

---

## Working Rules

- Keep first-phase scope tight.
- Do not add workflow steps in this phase.
- Do not add built-in workflows in this phase.
- Prefer small, testable public surfaces.
- Keep raw Slack API entities clearly separated from domain return models.
- Keep the configuration UX aligned with BYO Slack App + PKCE.
