#!/bin/bash
set -e

# FastAPI 서버만 실행 (추가적인 git clone, flutter pub get은 action 스크립트에서 진행)
mkdir -p ./src/dev
mkdir -p ./src/prod

echo "🚀 FastAPI 서버 실행 중..."
uvicorn main:app --host 0.0.0.0 --port 8000
