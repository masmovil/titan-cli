# Titan CLI - Development Guide (Initial Setup)

This guide covers the initial development setup for `titan-cli`, starting from its minimal "Hello World" implementation.

## 🚀 Quick Start

This section explains how to set up the project for development.

### Prerequisites
- Python 3.10+
- `pipx` (recommended for installation)

### Clone and Install

```bash
# Clone the repository
git clone <your-repo-url>
cd titan-cli

# Install in editable mode using pipx
# (This makes the 'titan' command available globally)
pipx install -e .

# Verify installation
titan
```
You should see the output: `Hola Mundo`

## 📦 Project Structure (Current)

The project currently has a minimal structure:

```
titan-cli/
├── titan_cli/              # Main package source
│   └── __main__.py         # CLI entry point ("Hola Mundo")
├── pyproject.toml          # Package configuration and dependencies
├── DEVELOPMENT.md          # This development guide
└── ... (other documentation files)
```

## 🛠️ Development Workflow

Because the project is installed in "editable" mode (`-e`), any changes you make to the Python source files will be reflected immediately when you run the `titan` command.

1.  **Edit the code:**
    ```bash
    # Open the entry point file in your editor
    vim titan_cli/__main__.py
    ```
2.  **Run the command:**
    ```bash
    # The changes are reflected instantly
    titan
    ```

This simple setup is the foundation. As we migrate more components (like the engine, UI, and plugins), this document will be updated.