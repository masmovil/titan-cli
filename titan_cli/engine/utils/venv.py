import os
from pathlib import Path
from subprocess import Popen, PIPE
from typing import Optional, Dict

def get_poetry_venv_env(cwd: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Detects the poetry virtual environment and returns a modified environment
    dictionary with the venv's bin path prepended to PATH.

    Args:
        cwd: The working directory to run poetry commands from.

    Returns:
        A dictionary for the 'env' parameter of subprocess calls, or None if
        the venv could not be determined.
    """
    process_env = os.environ.copy()
    try:
        env_proc = Popen(["poetry", "env", "info", "-p"], stdout=PIPE, stderr=PIPE, text=True, cwd=cwd)
        venv_path, _ = env_proc.communicate()

        if env_proc.returncode == 0 and venv_path.strip():
            bin_path = Path(venv_path.strip()) / "bin"
            process_env["PATH"] = f"{bin_path}:{process_env['PATH']}"
            return process_env
    except FileNotFoundError:
        # poetry command not found
        return None
    
    return None
