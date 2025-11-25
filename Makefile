# Titan CLI - Makefile
# Development commands for initial setup

.PHONY: help install clean

# Default target
help:
	@echo "Titan CLI - Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make install        Install in development mode using pipx"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          Remove basic build artifacts"

# Install in development mode using pipx
install:
	@echo "📦 Installing in development mode using pipx..."
	pipx install -e .
	@echo "✅ Installed. Run 'titan' to verify."

# Clean basic build artifacts
clean:
	@echo "🧹 Cleaning basic artifacts..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleaned"