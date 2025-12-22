# titan_cli/utils/cli_launcher.py
import subprocess
import sys
import shutil
from typing import Optional

class CLILauncher:
    """
    Generic launcher for external CLI tools.

    This class provides a standardized way to check for the availability of a CLI tool
    and launch it, optionally passing an initial prompt. It abstracts away the
    specific command-line arguments needed for interactive prompts for different tools.

    To integrate a new CLI tool:
    1. Ensure the tool is discoverable in the system's PATH.
    2. Add its configuration to `titan_cli/utils/cli_configs.py` within the `CLI_REGISTRY`.
       This configuration should include its `display_name`, `install_instructions` (optional),
       and `prompt_flag` (e.g., "-i" for Gemini, or None if it takes a positional argument).

    Attributes:
        cli_name (str): The actual command to execute (e.g., "claude", "gemini").
        install_instructions (Optional[str]): A message guiding the user on how to install the CLI.
        prompt_flag (Optional[str]): The command-line flag used by the CLI to accept an
                                       initial prompt while remaining interactive (e.g., "-i").
                                       If the CLI accepts a positional argument for the prompt, set to None.
    """

    def __init__(self, cli_name: str, install_instructions: Optional[str] = None, prompt_flag: Optional[str] = None):
        self.cli_name = cli_name
        self.install_instructions = install_instructions
        self.prompt_flag = prompt_flag

    def is_available(self) -> bool:
        """Check if the CLI tool is installed."""
        return shutil.which(self.cli_name) is not None

    def launch(self, prompt: Optional[str] = None, cwd: Optional[str] = None) -> int:
        """
        Launch the CLI tool in the current terminal.

        Args:
            prompt: Optional initial prompt to send to the CLI
            cwd: Working directory (default: current)

        Returns:
            Exit code from the CLI tool
        """
        cmd = [self.cli_name]

        if prompt:
            if self.prompt_flag:
                cmd.extend([self.prompt_flag, prompt])
            else:
                cmd.append(prompt)

        result = subprocess.run(
            cmd,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
            cwd=cwd
        )

        return result.returncode
