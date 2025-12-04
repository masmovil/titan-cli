# Titan CLI

> Development Tools Orchestrator

Titan CLI is a modular development tools orchestrator that streamlines your workflow through plugins, configuration management, and an intuitive terminal UI.

## ✨ Features

- 🔧 **Project Configuration Management** - Centralized `.titan/config.toml` for project settings
- 🔌 **Plugin System** - Extend functionality via entry points (GitHub, Git, Jira, AI)
- 🎨 **Rich Terminal UI** - Theme-aware components for beautiful CLI experiences
- 🤖 **AI Integration** - Optional AI assistance for code reviews and automation
- ⚡ **Workflow Engine** - Compose atomic steps into powerful workflows

## 🚀 Quick Start

### For Development (Contributors)

**Automated setup** (handles Poetry installation automatically):
```bash
git clone <repo>
cd titan-cli

# Choose one method:
make bootstrap          # Option 1: Using Make (simplest)
./bootstrap.sh         # Option 2: Interactive bash script
python3 setup.py       # Option 3: Advanced Python script
python3 -m titan_cli setup  # Option 4: Using Titan CLI itself
```

**Manual setup** (if you already have Poetry):
```bash
git clone <repo>
cd titan-cli
poetry install --with dev
poetry run titan
```

**Verify installation**:
```bash
make doctor            # Check system health
poetry run titan       # Run the CLI
```

### For End Users (Coming Soon)

```bash
# Install with pipx (recommended)
pipx install titan-cli

# Or with pip
pip install titan-cli
```

### Basic Usage

```bash
# Initialize global configuration
titan init

# List available projects
titan projects list

# Preview UI components
titan preview panel
titan preview menu
```

## 🔌 Plugins

Extend Titan CLI with plugins:

```bash
# Install a plugin
pipx inject titan-cli titan-plugin-github

# List installed plugins
titan plugins list
```

## Available plugins:

**Not available at the moment**

## 📚 Documentation

- **For AI Agents & Contributors**: See [AGENTS.md](AGENTS.md)
- **For Development**: See [DEVELOPMENT.md](DEVELOPMENT.md)
- **For Guides**: See [docs/guides/](docs/guides/)

## 🤝 Contributing

Contributions are welcome! Please see [AGENTS.md](AGENTS.md) for:
- Development setup
- Code style guidelines
- Testing requirements
- UI component patterns

## 📄 License

MIT License - see [LICENSE](LICENSE) for details

## 🙏 Acknowledgments

Built with:
- [Typer](https://typer.tiangolo.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal UI
- [Pydantic](https://docs.pydantic.dev/) - Data validation
