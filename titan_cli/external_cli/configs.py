# titan_cli/utils/cli_configs.py
"""
Centralized registry for external CLI tool configurations.
"""

CLI_REGISTRY = {
    "claude": {
        "display_name": "Claude CLI",
        "install_instructions": "Install: npm install -g @anthropic/claude-code",
        "prompt_flag": None
    },
    "gemini": {
        "display_name": "Gemini CLI",
        "install_instructions": None,
        "prompt_flag": "-i"
    }
}
