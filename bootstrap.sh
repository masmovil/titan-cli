#!/usr/bin/env bash

# Titan CLI Bootstrap Script
# Automatically installs dependencies and sets up the development environment

set -e  # Exit on error

echo "🚀 Titan CLI Bootstrap"
echo "===================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo "📋 Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed${NC}"
    echo "Please install Python 3.10 or higher from https://www.python.org"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
REQUIRED_VERSION="3.10"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}❌ Python $PYTHON_VERSION is too old${NC}"
    echo "Python $REQUIRED_VERSION or higher is required"
    exit 1
fi

echo -e "${GREEN}✅ Python $PYTHON_VERSION${NC}"
echo ""

# Check/Install Poetry
echo "📦 Checking Poetry..."
if command -v poetry &> /dev/null; then
    POETRY_VERSION=$(poetry --version | cut -d' ' -f3 | tr -d ')')
    echo -e "${GREEN}✅ Poetry $POETRY_VERSION already installed${NC}"
else
    echo -e "${YELLOW}⚠️  Poetry not found, installing...${NC}"
    curl -sSL https://install.python-poetry.org | python3 -

    # Add to PATH for current session
    export PATH="$HOME/.local/bin:$PATH"

    if command -v poetry &> /dev/null; then
        echo -e "${GREEN}✅ Poetry installed successfully${NC}"
    else
        echo -e "${RED}❌ Poetry installation failed${NC}"
        exit 1
    fi

    # Detect shell and offer to add to profile
    echo ""
    echo -e "${YELLOW}📝 Poetry needs to be added to your PATH${NC}"
    SHELL_NAME=$(basename "$SHELL")

    case "$SHELL_NAME" in
        bash)
            PROFILE="$HOME/.bashrc"
            ;;
        zsh)
            PROFILE="$HOME/.zshrc"
            ;;
        fish)
            PROFILE="$HOME/.config/fish/config.fish"
            ;;
        *)
            PROFILE="$HOME/.profile"
            ;;
    esac

    echo "Detected shell: $SHELL_NAME"
    read -p "Add Poetry to $PROFILE? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "" >> "$PROFILE"
        echo "# Added by Titan CLI bootstrap" >> "$PROFILE"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$PROFILE"
        echo -e "${GREEN}✅ Added to $PROFILE${NC}"
        echo -e "${YELLOW}⚠️  Run: source $PROFILE${NC}"
    else
        echo -e "${YELLOW}⚠️  Skipped. Add this to your shell profile manually:${NC}"
        echo 'export PATH="$HOME/.local/bin:$PATH"'
    fi
fi

echo ""

# Install project dependencies
echo "📚 Installing project dependencies..."
poetry install --with dev

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Dependencies installed successfully${NC}"
else
    echo -e "${RED}❌ Failed to install dependencies${NC}"
    exit 1
fi

echo ""

# Verify installation
echo "🔍 Verifying installation..."
if poetry run titan --version &> /dev/null; then
    VERSION=$(poetry run titan --version 2>&1 || echo "unknown")
    echo -e "${GREEN}✅ Titan CLI is ready!${NC}"
    echo "Version: $VERSION"
else
    echo -e "${RED}❌ Verification failed${NC}"
    exit 1
fi

echo ""
echo "🎉 Bootstrap complete!"
echo ""
echo "Next steps:"
echo "  1. Run: poetry run titan"
echo "  2. Or activate the virtual environment: poetry shell"
echo "  3. Then run: titan"
echo ""
