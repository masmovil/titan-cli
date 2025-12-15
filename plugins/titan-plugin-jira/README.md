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

Configure in `.titan/config.toml`:

```toml
[jira]
base_url = "https://your-domain.atlassian.net"
email = "your-email@example.com"
api_token = "your-api-token"
default_project = "PROJECT"
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
