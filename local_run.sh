#!/bin/bash
set -e

echo "📦 Python 가상환경 준비 중..."
python3 -m venv venv
source venv/bin/activate

echo "📦 pip 최신화 및 requirements.txt 설치 중..."
pip install --upgrade pip
pip install -r requirements.txt

# .env 파일을 읽어와서 모든 변수를 환경변수 설정
set -a
[ -f .env ] && . .env
set +a

mkdir -p ./src/dev
mkdir -p ./src/stage
mkdir -p ./src/prod

echo "🚀 FastAPI 서버 실행 중..."
uvicorn main:app --reload --host 0.0.0.0 --port 8000
