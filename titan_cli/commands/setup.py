"""
Setup command - Automated development environment setup

Runs the bootstrap script to install Poetry and dependencies automatically.
"""
import typer
import subprocess
import sys
from pathlib import Path
from titan_cli.ui.components.typography import TextRenderer
from titan_cli.messages import msg


setup_app = typer.Typer(
    name="setup",
    help="Automated development environment setup",
    invoke_without_command=True,
)


@setup_app.callback()
def setup_command():
    """
    Run automated setup to install Poetry and project dependencies.

    This command executes the bootstrap script which:
    - Checks Python version (3.10+ required)
    - Installs Poetry if not present
    - Configures shell PATH
    - Installs all project dependencies
    - Verifies the installation

    Equivalent to running: ./bootstrap.sh or make bootstrap
    """
    text = TextRenderer()

    # Get the project root (where bootstrap.sh is located)
    project_root = Path(__file__).parent.parent.parent
    bootstrap_script = project_root / "bootstrap.sh"

    if not bootstrap_script.exists():
        text.error(f"Bootstrap script not found at: {bootstrap_script}")
        text.body("This command only works when running from the development repository.")
        text.body("If you installed Titan CLI with pipx/pip, dependencies are already installed.")
        raise typer.Exit(1)

    text.title("🚀 Titan CLI Setup")
    text.body("Running automated development environment setup...")
    text.line()

    try:
        # Run the bootstrap script
        result = subprocess.run(
            ["bash", str(bootstrap_script)],
            cwd=str(project_root),
            check=False
        )

        if result.returncode == 0:
            text.line()
            text.success("✅ Setup completed successfully!")
            text.body("You can now use: poetry run titan")
        else:
            text.line()
            text.error(f"❌ Setup failed with exit code {result.returncode}")
            text.body("Please check the error messages above and try again.")
            raise typer.Exit(result.returncode)

    except FileNotFoundError:
        text.error("❌ bash command not found")
        text.body("Please install bash or run the setup manually:")
        text.body(f"  python3 {project_root / 'setup.py'}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        text.line()
        text.warning("⚠️  Setup cancelled by user")
        raise typer.Exit(130)
