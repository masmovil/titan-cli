# Titan Plugin - JIRA

JIRA integration plugin for Titan CLI with AI-powered issue management.

## Features

- JIRA issue search and management
- AI-powered requirements analysis
- Workflow automation
- Issue creation and tracking

## Installation

This plugin is installed automatically with Titan CLI when configured with JIRA credentials.

## Configuration

### Global Configuration (Required)

Configure your JIRA credentials in `~/.titan/config.toml` (user-level):

```toml
[plugins.jira]
enabled = true

[plugins.jira.config]
base_url = "https://your-domain.atlassian.net"
email = "your-email@example.com"
```

**API Token** must be stored in secrets (secure storage):
- Use `titan configure jira` to set up securely
- Or set environment variable `JIRA_API_TOKEN`

### Project Configuration (Optional)

Override project-specific settings in `.titan/config.toml`:

```toml
[plugins.jira]
enabled = true

[plugins.jira.config]
default_project = "ECAPP"  # Project-specific default
```

## Usage

Available workflows:
- Analyze JIRA Issues - Search and analyze issues with AI

## Development

Run tests:
```bash
cd plugins/titan-plugin-jira
poetry run pytest
```
