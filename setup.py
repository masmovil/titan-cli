#!/usr/bin/env python3
"""
Titan CLI Setup Script
Advanced bootstrapper with dependency checking and installation
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple


class Colors:
    """ANSI color codes"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


def print_status(message: str, status: str = "info"):
    """Print colored status message"""
    color_map = {
        "success": Colors.GREEN,
        "error": Colors.RED,
        "warning": Colors.YELLOW,
        "info": Colors.BLUE,
    }
    color = color_map.get(status, Colors.NC)
    symbols = {
        "success": "✅",
        "error": "❌",
        "warning": "⚠️ ",
        "info": "ℹ️ ",
    }
    symbol = symbols.get(status, "→")
    print(f"{color}{symbol} {message}{Colors.NC}")


def run_command(cmd: list[str], capture: bool = True) -> Tuple[int, str]:
    """Run shell command and return exit code and output"""
    try:
        if capture:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode, result.stdout.strip()
        else:
            result = subprocess.run(cmd, check=False)
            return result.returncode, ""
    except Exception as e:
        return 1, str(e)


def check_python_version() -> bool:
    """Check if Python version is compatible"""
    print_status("Checking Python version...", "info")

    major, minor = sys.version_info[:2]
    version_str = f"{major}.{minor}"

    if major < 3 or (major == 3 and minor < 10):
        print_status(f"Python {version_str} is too old. Python 3.10+ required.", "error")
        return False

    print_status(f"Python {version_str} OK", "success")
    return True


def check_poetry() -> Optional[str]:
    """Check if Poetry is installed and return version"""
    print_status("Checking Poetry...", "info")

    poetry_path = shutil.which("poetry")
    if not poetry_path:
        return None

    code, output = run_command(["poetry", "--version"])
    if code == 0:
        # Extract version from "Poetry (version X.Y.Z)"
        version = output.split()[-1].strip('()')
        print_status(f"Poetry {version} found at {poetry_path}", "success")
        return version

    return None


def install_poetry() -> bool:
    """Install Poetry using official installer"""
    print_status("Installing Poetry...", "warning")

    # Download and run installer
    code, _ = run_command([
        "curl", "-sSL",
        "https://install.python-poetry.org"
    ], capture=False)

    if code != 0:
        print_status("Failed to download Poetry installer", "error")
        return False

    # Verify installation
    poetry_bin = Path.home() / ".local" / "bin" / "poetry"
    if not poetry_bin.exists():
        print_status("Poetry binary not found after installation", "error")
        return False

    # Add to PATH for current process
    os.environ["PATH"] = f"{poetry_bin.parent}:{os.environ['PATH']}"

    print_status("Poetry installed successfully", "success")
    return True


def add_poetry_to_shell() -> bool:
    """Offer to add Poetry to shell profile"""
    print()
    print_status("Poetry needs to be added to your PATH", "warning")

    shell = os.environ.get("SHELL", "")
    shell_name = Path(shell).name if shell else "unknown"

    # Determine profile file
    profile_map = {
        "bash": Path.home() / ".bashrc",
        "zsh": Path.home() / ".zshrc",
        "fish": Path.home() / ".config" / "fish" / "config.fish",
    }
    profile = profile_map.get(shell_name, Path.home() / ".profile")

    print(f"Detected shell: {shell_name}")
    response = input(f"Add Poetry to {profile}? (y/n) ").strip().lower()

    if response == 'y':
        try:
            with open(profile, 'a') as f:
                f.write('\n# Added by Titan CLI setup\n')
                f.write('export PATH="$HOME/.local/bin:$PATH"\n')
            print_status(f"Added to {profile}", "success")
            print_status(f"Run: source {profile}", "warning")
            return True
        except Exception as e:
            print_status(f"Failed to update {profile}: {e}", "error")
            return False
    else:
        print_status("Skipped. Add this manually to your shell profile:", "warning")
        print('export PATH="$HOME/.local/bin:$PATH"')
        return False


def install_dependencies() -> bool:
    """Install project dependencies with Poetry"""
    print()
    print_status("Installing project dependencies...", "info")

    code, _ = run_command(
        ["poetry", "install", "--with", "dev"],
        capture=False
    )

    if code != 0:
        print_status("Failed to install dependencies", "error")
        return False

    print_status("Dependencies installed successfully", "success")
    return True


def verify_installation() -> bool:
    """Verify Titan CLI is working"""
    print()
    print_status("Verifying installation...", "info")

    code, output = run_command(["poetry", "run", "titan", "version"])
    if code != 0:
        print_status("Titan CLI verification failed", "error")
        return False

    print_status(f"Titan CLI is ready! {output}", "success")
    return True


def main():
    """Main setup routine"""
    print("🚀 Titan CLI Setup")
    print("=" * 50)
    print()

    # Check Python
    if not check_python_version():
        sys.exit(1)

    print()

    # Check/Install Poetry
    poetry_version = check_poetry()
    if not poetry_version:
        if not install_poetry():
            sys.exit(1)
        if not add_poetry_to_shell():
            print()
            print_status("Continue anyway...", "warning")

    # Install dependencies
    if not install_dependencies():
        sys.exit(1)

    # Verify
    if not verify_installation():
        sys.exit(1)

    # Success message
    print()
    print("🎉 Setup complete!")
    print()
    print("Next steps:")
    print("  1. Run: poetry run titan")
    print("  2. Or activate virtual environment: poetry shell")
    print("  3. Then run: titan")
    print()


if __name__ == "__main__":
    main()
