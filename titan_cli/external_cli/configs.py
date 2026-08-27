# titan_cli/utils/cli_configs.py
"""
Centralized registry for external CLI tool configurations.
"""

CLI_REGISTRY = {
    "claude": {
        "display_name": "Claude CLI",
        "install_instructions": "Install: npm install -g @anthropic/claude-code",
        "prompt_flag": None,
        "model_flag": "--model"
    },
    "gemini": {
        "display_name": "Gemini CLI",
        "install_instructions": None,
        "prompt_flag": "-i",
        "model_flag": "-m"
    },
    "codex": {
        "display_name": "Codex CLI",
        "install_instructions": "Install: pip install openai[cli]",
        "prompt_flag": None,
        "model_flag": "-m"
    }
}
