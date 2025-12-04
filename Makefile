# Titan CLI - Makefile
# Development commands for setup and management

.PHONY: help bootstrap setup install test clean doctor

# Default target
help:
	@echo "Titan CLI - Available commands:"
	@echo ""
	@echo "Setup:"
	@echo "  make bootstrap      Auto-install all dependencies (Poetry, packages)"
	@echo "  make setup          Install project dependencies (requires Poetry)"
	@echo "  make install        Install in development mode using pipx"
	@echo ""
	@echo "Development:"
	@echo "  make test           Run tests"
	@echo "  make doctor         Check system health"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          Remove build artifacts"

# Bootstrap - auto-install everything
bootstrap:
	@echo "🚀 Running bootstrap script..."
	@bash bootstrap.sh

# Setup - install dependencies with Poetry (requires Poetry installed)
setup:
	@echo "📦 Installing dependencies with Poetry..."
	@command -v poetry >/dev/null 2>&1 || { echo "❌ Poetry not found. Run 'make bootstrap' first."; exit 1; }
	poetry install --with dev
	@echo "✅ Setup complete. Run 'poetry run titan' to start."

# Install in development mode using pipx (alternative)
install:
	@echo "📦 Installing in development mode using pipx..."
	pipx install -e .
	@echo "✅ Installed. Run 'titan' to verify."

# Run tests
test:
	@echo "🧪 Running tests..."
	poetry run pytest

# Check system health
doctor:
	@echo "🔍 Checking system health..."
	@echo ""
	@echo "Python:"
	@python3 --version || echo "❌ Python not found"
	@echo ""
	@echo "Poetry:"
	@export PATH="$$HOME/.local/bin:$$PATH" && poetry --version 2>/dev/null || echo "❌ Poetry not found"
	@echo ""
	@echo "Titan CLI:"
	@if [ -d "$$(export PATH="$$HOME/.local/bin:$$PATH" && poetry env info -p 2>/dev/null)" ]; then \
		export PATH="$$HOME/.local/bin:$$PATH" && poetry run titan version 2>/dev/null || echo "⚠️  Installed but not working"; \
	else \
		echo "❌ Not installed (run 'make setup')"; \
	fi
	@echo ""

# Clean build artifacts
clean:
	@echo "🧹 Cleaning artifacts..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleaned"