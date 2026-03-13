#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "📦 Preparing local environment..."
if [ ! -d venv ]; then
    python3 -m venv venv
fi

source venv/bin/activate
python -m pip install --upgrade pip
set -o pipefail
python -m pip install -r requirements.txt | { grep -v "already satisfied" || :; }

if [ ! -f .env ]; then
    echo "⚠️ .env 파일이 없습니다. env.template 또는 env.sample을 참고해 생성하세요."
fi

if [ "${RUN_NGROK:-0}" = "1" ]; then
    if ! command -v ngrok >/dev/null 2>&1; then
        echo "❌ RUN_NGROK=1 이지만 ngrok가 설치되어 있지 않습니다."
        exit 1
    fi
    echo "🌐 Starting ngrok in background..."
    ngrok http "${PORT:-8000}" > /tmp/local-flutter-cicd-ngrok.log 2>&1 &
    echo "   Log: /tmp/local-flutter-cicd-ngrok.log"
fi

echo "🚀 Starting FastAPI server..."
exec ./venv/bin/uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"
