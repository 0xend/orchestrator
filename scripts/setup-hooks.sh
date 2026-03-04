#!/bin/bash

# Setup git hooks for the project
# Run this after cloning the repository

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$(git rev-parse --git-dir)/hooks"
SCRIPTS_DIR="$REPO_ROOT/scripts"

echo "Setting up git hooks..."
mkdir -p "$HOOKS_DIR"

# Copy pre-commit hook
cp "$SCRIPTS_DIR/pre-commit" "$HOOKS_DIR/pre-commit"
chmod +x "$HOOKS_DIR/pre-commit"

# Copy pre-push hook
cp "$SCRIPTS_DIR/pre-push" "$HOOKS_DIR/pre-push"
chmod +x "$HOOKS_DIR/pre-push"

echo "✅ Git hooks installed successfully!"
echo ""
echo "The following hooks are now active:"
echo "  - pre-commit: Runs local commit-time checks before committing"
echo "  - pre-push: Runs CI-equivalent checks (unit + E2E) before pushing"
echo ""
echo "To skip hooks temporarily, use: git commit --no-verify or git push --no-verify"
