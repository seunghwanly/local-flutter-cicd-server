#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "📦 Installing local Flutter CI/CD environment..."
./scripts/start.sh --bootstrap-only

echo ""
echo "🩺 Running repository checks..."
make doctor
make test

echo ""
echo "✅ Install completed."
echo "Next commands:"
echo "  make run"
echo "  curl http://localhost:8000/diagnostics"
