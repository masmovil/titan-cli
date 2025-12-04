# Installation Guide

Quick installation guide for Titan CLI contributors and developers.

## Prerequisites

- **Python 3.10+** (check with `python3 --version`)
- **Git** (for cloning the repository)

## Quick Setup (Recommended)

The easiest way to get started is using our automated setup tools:

### Option 1: Make (Simplest)

```bash
git clone <repository-url>
cd titan-cli
make bootstrap
```

This will:
- ✅ Check Python version
- ✅ Install Poetry if needed
- ✅ Configure your shell PATH
- ✅ Install all dependencies
- ✅ Verify the installation

### Option 2: Titan CLI Command (Recommended for contributors)

```bash
git clone <repository-url>
cd titan-cli
python3 -m titan_cli setup
```

Uses Titan's built-in setup command. Same functionality as make bootstrap.

### Option 3: Bash Script

```bash
git clone <repository-url>
cd titan-cli
./bootstrap.sh
```

Interactive setup with colored output and step-by-step prompts.

### Option 4: Python Script

```bash
git clone <repository-url>
cd titan-cli
python3 setup.py
```

Advanced setup with comprehensive checks and error handling.

## Manual Setup

If you already have Poetry installed and configured:

```bash
git clone <repository-url>
cd titan-cli
poetry install --with dev
```

## Verify Installation

Check that everything is working:

```bash
make doctor
```

Expected output:
```
🔍 Checking system health...

Python:
Python 3.12.x

Poetry:
Poetry (version 2.2.x)

Titan CLI:
Titan CLI v0.1.0
```

## Running Titan CLI

### During Development

```bash
# Run directly with Poetry
poetry run titan

# Or activate the virtual environment first
poetry shell
titan
```

### Available Commands

```bash
make help          # Show all available commands
make test          # Run tests
make doctor        # Check system health
make clean         # Clean build artifacts
```

## Common Issues

### Poetry not found

**Problem**: `poetry: command not found`

**Solution**: Add Poetry to your PATH:

```bash
# For bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# For zsh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Python version too old

**Problem**: `Python 3.9 is too old`

**Solution**: Install Python 3.10+ from:
- macOS: `brew install python@3.12`
- Linux: `sudo apt install python3.12` or `sudo yum install python3.12`
- Windows: Download from [python.org](https://www.python.org)

### Permission errors during setup

**Problem**: Permission denied errors

**Solution**: Don't use `sudo` with Poetry or pip. Poetry installs to your user directory.

## Alternative: pipx Installation (Not Recommended for Development)

If you prefer using pipx for an isolated global installation:

```bash
# Install pipx if needed
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install titan-cli
cd titan-cli
pipx install -e .
```

**Note**: This method doesn't support development dependencies or easy testing.

## Next Steps

After successful installation:

1. Read [AGENTS.md](AGENTS.md) for contributor guidelines
2. Read [DEVELOPMENT.md](DEVELOPMENT.md) for architecture overview
3. Run `titan init` to configure your global settings
4. Run `titan projects list` to discover projects

## Getting Help

- Check the [documentation](docs/)
- Review [AGENTS.md](AGENTS.md) for detailed development info
- Open an issue on GitHub

---

**Last Updated**: 2025-12-04
