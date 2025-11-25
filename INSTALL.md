# Titan CLI - Installation Guide (Initial Setup)

This guide covers the installation for the current development version of `titan-cli`.

## Prerequisites

- Python 3.10+
- `pipx`

If you don't have `pipx`, you can install it with:
```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```
*Note: You may need to restart your shell for `pipx` to be available in your PATH.*

## Installation from Source

As the project is under active development and not yet on PyPI, it must be installed from a local clone of the repository.

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd titan-cli
    ```

2.  **Install in editable mode using `pipx`:**
    This command installs `titan-cli` in an isolated environment and makes the `titan` command available globally in your terminal.
    ```bash
    pipx install -e .
    ```

## Verification

After installation, run the command to verify it works:

```bash
titan
```

You should see the following output:
```
Hola Mundo
```

## Updating

Since the installation points to your local repository, simply pull the latest changes:

```bash
cd titan-cli
git pull
```
`pipx` will automatically use the updated code since it's an "editable" install.