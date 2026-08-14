# Installation

## Requirements

- Python 3.11 or later
- macOS, Linux, or Windows (WSL2 recommended on Windows)

---

## Install with pipx (recommended)

[pipx](https://pipx.pypa.io/) installs Titan in an isolated environment and puts it on your `PATH` automatically — no virtualenv management needed.

```bash
# Install pipx if you don't have it
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install Titan
pipx install titan-cli
```

Verify:

```bash
titan --version
```

---

## Install with pip

If you prefer a regular pip install into an existing environment:

```bash
pip install titan-cli
```

!!! warning
    Using pip directly can create dependency conflicts with other packages. pipx is strongly recommended.

---

## First launch

Run Titan from inside a project directory:

```bash
cd /path/to/your-project
titan
```

On first launch, two setup wizards run automatically:

1. **Global setup** — Configure AI connections. This is optional and can be skipped.
2. **Project setup** — Choose a project name and enable the plugins you want (Git, GitHub, Jira).

After setup, the main menu appears and you're ready to run workflows.

---

## What gets created

| Path | Purpose |
|------|---------|
| `~/.titan/config.toml` | Global config: AI connections and credentials |
| `.titan/config.toml` | Project config: enabled plugins and settings |

The project config lives at the **git repository root**, so it works correctly in monorepos.

---

## Next step

[→ Quick Start](quick-start.md) — Learn the basics of the Titan interface.
