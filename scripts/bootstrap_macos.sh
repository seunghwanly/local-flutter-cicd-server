#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require_command() {
    local command_name="$1"
    local install_hint="$2"
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "❌ Missing required command: $command_name"
        echo "   Install: $install_hint"
        exit 1
    fi
}

echo "🔎 Checking macOS development prerequisites..."
require_command "python3" "brew install python"
require_command "git" "xcode-select --install"

if ! command -v brew >/dev/null 2>&1; then
    echo "❌ Homebrew is required for the recommended macOS bootstrap flow."
    echo "   Install: https://brew.sh"
    exit 1
fi

echo "📦 Preparing Python virtualenv..."
cd "$ROOT_DIR"
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ ! -f .env ]; then
    echo "📄 Creating .env from env.template"
    cp env.template .env
fi

echo "🔎 Checking optional toolchain..."
for tool_name in fvm ruby bundle pod ngrok; do
    if command -v "$tool_name" >/dev/null 2>&1; then
        echo "✅ $tool_name"
    else
        echo "⚠️ Missing optional command: $tool_name"
    fi
done

echo ""
echo "Bootstrap complete."
echo "Next steps:"
echo "  1. Fill in .env with real values"
echo "  2. Run: make run"
echo "  3. Optional webhook tunnel: ngrok http 8000"
