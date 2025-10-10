#!/bin/bash
set -e

echo "📦 Python 가상환경 준비 중..."
python3 -m venv venv
source venv/bin/activate

echo "📦 pip 최신화 및 requirements.txt 설치 중..."
pip install --upgrade pip
set -o pipefail; pip install -r requirements.txt | { grep -v "already satisfied" || :; }

# .env 파일을 읽어와서 모든 변수를 환경변수 설정
if [ -f .env ]; then
    echo "📄 .env 파일 로드 중..."
    set -a
    source .env
    set +a
else
    echo "⚠️ .env 파일이 없습니다. env.template을 참고하여 .env 파일을 생성하세요."
fi

# 가상환경 활성화 확인
if [ -z "$VIRTUAL_ENV" ]; then
    echo "❌ 가상환경이 활성화되지 않았습니다."
    exit 1
fi

echo "🚀 FastAPI 서버 실행 중..."
echo "📍 가상환경: $VIRTUAL_ENV"
echo "📍 Python 경로: $(which python3)"

uvicorn src.main:app --port 8000
