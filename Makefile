# Titan CLI - Makefile
# Development commands for initial setup

.PHONY: help install dev-install test check-github clean docs-serve docs-build docs-deploy

# Default target
help:
	@echo "Titan CLI - Available commands:"
	@echo ""
	@echo "For Contributors:"
	@echo "  make dev-install    Setup development environment (creates titan-dev)"
	@echo "  make test           Run all tests"
	@echo "  make check-github   Ruff + pytest for titan-plugin-github only"
	@echo ""
	@echo "For Users:"
	@echo "  make install        Install production version (NOT recommended - use pipx)"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs-serve     Serve docs locally at http://localhost:8000"
	@echo "  make docs-build     Build docs to site/"
	@echo "  make docs-deploy    Deploy docs to GitHub Pages"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          Remove basic build artifacts"
	@echo ""
	@echo "Note: Contributors should use 'make dev-install' to get titan-dev command."
	@echo "      End users should use 'pipx install titan-cli' instead."

# Setup development environment (CONTRIBUTORS ONLY)
dev-install:
	@echo "🔧 Setting up development environment..."
	@echo ""
	@echo "1️⃣  Installing dependencies with Poetry..."
	poetry install
	@echo ""
	@echo "2️⃣  Creating titan-dev launcher..."
	@mkdir -p ~/.local/bin
	@echo '#!/bin/bash' > ~/.local/bin/titan-dev
	@echo '# titan-dev - Development version of Titan CLI' >> ~/.local/bin/titan-dev
	@echo 'export TITAN_ENV=development' >> ~/.local/bin/titan-dev
	@echo 'exec "$(shell pwd)/.venv/bin/titan" "$$@"' >> ~/.local/bin/titan-dev
	@chmod +x ~/.local/bin/titan-dev
	@echo ""
	@echo "✅ Development environment ready!"
	@echo ""
	@echo "Usage:"
	@echo "  titan-dev           Run development version from local codebase"
	@echo "  poetry run titan    Alternative way to run"
	@echo ""
	@echo "Verify installation:"
	@~/.local/bin/titan-dev --version || echo "⚠️  Make sure ~/.local/bin is in your PATH"

# Install production version (NOT recommended - use pipx instead)
install:
	@echo "⚠️  This installs from local source, not PyPI."
	@echo "⚠️  For production use: pipx install titan-cli"
	@echo ""
	@echo "📦 Installing from local source..."
	pipx install .
	@echo "✅ Installed. Run 'titan' to verify."

# Run tests
test:
	@echo "🧪 Running all tests..."
	poetry run pytest

# Ruff + pytest for the GitHub plugin only (faster loop while working on it)
check-github:
	poetry run ruff check plugins/titan-plugin-github/
	poetry run pytest plugins/titan-plugin-github/tests -q

# Docs commands
docs-serve:
	@echo "📖 Serving docs at http://localhost:8000 ..."
	poetry run mkdocs serve

docs-build:
	@echo "📖 Building docs to site/ ..."
	poetry run mkdocs build

docs-deploy:
	@echo "🚀 Deploying docs to GitHub Pages ..."
	poetry run mkdocs gh-deploy

# Clean basic build artifacts
clean:
	@echo "🧹 Cleaning basic artifacts..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleaned"