#!/bin/bash

set -ex

# Record start time for performance measurement
BUILD_START_TIME=$(date +%s)

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed. Please install uv first:"
    echo "curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "=================================================="
echo "SONiC Bug Handler Standalone Build Script"
echo "Using uv for fast dependency management"
echo "=================================================="
echo "Start time: $(date)"
echo "uv version: $(uv --version)"

# Backup original __init__.py files to avoid module loading issues
echo "Backing up __init__.py files..."
cp ../../../__init__.py ../../../__init__.py.1
cp ../__init__.py ../__init__.py.1

# Clean up __init__.py files to prevent loading unneeded modules during build
echo "Cleaning up __init__.py files to avoid loading unneeded modules..."
echo "" > ../../../__init__.py
echo "" > ../__init__.py

# Cleanup function to restore original files
cleanup() {
    echo "Restoring original __init__.py files..."
    mv ../../../__init__.py.1 ../../../__init__.py
    mv ../__init__.py.1 ../__init__.py
    echo "Cleanup completed."
}

# Ensure cleanup runs on script exit
trap cleanup EXIT

# Use uv to create virtual environment and install dependencies
if [[ -d ".venv" ]]; then
    echo "Using existing virtual environment at .venv..."
else
    echo "Creating new virtual environment with uv..."
    uv venv --python 3.12 .venv
fi

# Install dependencies using uv (much faster than pip)
# Check if pyproject.toml exists and use it, otherwise fall back to requirements.txt
if [[ -f "pyproject.toml" ]]; then
    echo "Found pyproject.toml - installing dependencies with uv sync..."
    uv sync
else
    echo "Using requirements.txt - installing dependencies with uv pip..."
    uv pip install -r requirements.txt
fi

# Build standalone executable with PyInstaller
echo "Building standalone bug handler executable..."
uv run pyinstaller bug_handler.spec --noconfirm --clean

# Verify build artifacts exist
if [[ ! -f "./dist/bug_handler/bug_handler" ]]; then
    echo "Error: Build failed - bug_handler executable not found"
    exit 1
fi

if [[ ! -d "./dist/bug_handler/_internal" ]]; then
    echo "Error: Build failed - _internal directory not found"
    exit 1
fi

# Set executable permissions on the built binary
chmod +x ./dist/bug_handler/bug_handler

echo "Build completed successfully!"
echo "Standalone bug handler is available at: ./dist/bug_handler/bug_handler"


# Calculate and display build time
BUILD_END_TIME=$(date +%s)
BUILD_DURATION=$((BUILD_END_TIME - BUILD_START_TIME))

# Display final information
echo "=================================================="
echo "Bug handler build process completed successfully!"
echo "=================================================="
echo "End time: $(date)"
echo "Total build time: ${BUILD_DURATION} seconds"
echo ""
echo "Build artifacts:"
echo "  Executable: ./dist/bug_handler/bug_handler"
echo "  Dependencies: ./dist/bug_handler/_internal/"
echo ""
echo "Usage:"
echo "  ./dist/bug_handler/bug_handler --help"
echo "=================================================="
