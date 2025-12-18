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
    
    # DATADOG_API_KEY가 있으면 명시적으로 export
    if [ ! -z "$DATADOG_API_KEY" ]; then
        export DATADOG_API_KEY="$DATADOG_API_KEY"
        echo "✅ DATADOG_API_KEY 환경변수 설정 완료"
    fi
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

# 서버를 백그라운드에서 실행
uvicorn src.main:app --port 8000 &

# 서버가 시작될 때까지 잠시 대기
sleep 3

# 새로운 터미널 탭에서 ngrok 실행
echo "🌐 ngrok 터널링 시작 중..."
osascript -e "tell application \"Terminal\" to do script \"cd $(pwd) && ngrok http 8000 --url https://known-manually-cicada.ngrok-free.app\""

# 포그라운드에서 서버 프로세스 대기 (Ctrl+C로 종료 가능)
wait
