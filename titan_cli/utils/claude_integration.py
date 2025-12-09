# titan_cli/utils/claude_integration.py
import subprocess
import sys
import shutil
from typing import Optional

class ClaudeCodeLauncher:
    """Launch Claude Code CLI from Titan and return when done."""

    @staticmethod
    def is_available() -> bool:
        """Check if Claude Code is installed."""
        return shutil.which("claude") is not None

    @staticmethod
    def launch(prompt: Optional[str] = None, cwd: Optional[str] = None) -> int:
        """
        Launch Claude Code CLI in current terminal.
        
        Args:
            prompt: Optional initial prompt to send to Claude
            cwd: Working directory (default: current)
            
        Returns:
            Exit code from Claude Code
        """
        cmd = ["claude"]

        if prompt:
            cmd.extend(["--prompt", prompt])

        # Execute in interactive mode, passing through terminal I/O
        result = subprocess.run(
            cmd,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
            cwd=cwd
        )

        return result.returncode
