#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
RUNTIME_DIR="$ROOT_DIR/.workspace/runtime"
PID_FILE="$RUNTIME_DIR/server.pid"
LOG_FILE="$RUNTIME_DIR/server.log"
MODE="background"
BOOTSTRAP_ONLY=0
SYNC_MAIN=0

usage() {
    cat <<'EOF'
Usage: ./scripts/start.sh [--foreground] [--background] [--bootstrap-only] [--sync-main]

Options:
  --foreground      Run uvicorn in the current terminal.
  --background      Restart the repo server in the background (default).
  --bootstrap-only  Prepare venv and dependencies, then exit.
  --sync-main       Fetch and pull origin/main before starting.
EOF
}

for arg in "$@"; do
    case "$arg" in
        --foreground)
            MODE="foreground"
            ;;
        --background)
            MODE="background"
            ;;
        --bootstrap-only)
            BOOTSTRAP_ONLY=1
            ;;
        --sync-main)
            SYNC_MAIN=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "❌ Unknown option: $arg"
            usage
            exit 1
            ;;
    esac
done

mkdir -p "$RUNTIME_DIR"

require_command() {
    local command_name="$1"
    local install_hint="$2"
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "❌ Missing required command: $command_name"
        echo "   Install: $install_hint"
        exit 1
    fi
}

prepare_env() {
    echo "📦 Preparing local environment..."
    require_command "python3" "brew install python"
    require_command "git" "xcode-select --install"

    cd "$ROOT_DIR"

    if [ ! -d venv ]; then
        python3 -m venv venv
    fi

    source venv/bin/activate
    python -m pip install --upgrade pip >/dev/null
    set -o pipefail
    python -m pip install -r requirements.txt | { grep -v "already satisfied" || :; }

    if [ ! -f .env ]; then
        if [ -f env.template ]; then
            cp env.template .env
            echo "📄 Created .env from env.template"
        else
            echo "⚠️ .env 파일이 없습니다."
        fi
    fi
}

ensure_clean_worktree() {
    if [ -n "$(git status --porcelain)" ]; then
        echo "❌ 작업 트리가 깨끗하지 않습니다. 변경사항을 정리한 뒤 다시 시도하세요."
        git status --short
        exit 1
    fi
}

sync_main_branch() {
    ensure_clean_worktree
    echo "🔄 origin/main 최신 상태를 가져옵니다..."
    git fetch origin
    git checkout main
    git pull origin main
}

stop_existing_server() {
    local pids
    pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN || true)"

    if [ -z "$pids" ]; then
        rm -f "$PID_FILE"
        return
    fi

    echo "🛑 포트 $PORT 에서 실행 중인 서버를 확인합니다..."

    for pid in $pids; do
        local command
        command="$(ps -p "$pid" -o command= 2>/dev/null || true)"

        if [[ "$command" != *"$ROOT_DIR"* && "$command" != *"uvicorn src.main:app"* && "$command" != *"scripts/start.sh"* ]]; then
            echo "❌ 포트 $PORT 를 사용 중인 프로세스가 이 저장소의 서버로 보이지 않습니다."
            echo "   PID: $pid"
            echo "   CMD: $command"
            exit 1
        fi

        echo "   종료 중: PID $pid"
        kill "$pid"
    done

    for pid in $pids; do
        local wait_count=0
        while kill -0 "$pid" 2>/dev/null; do
            if [ "$wait_count" -ge 30 ]; then
                echo "   강제 종료: PID $pid"
                kill -9 "$pid" 2>/dev/null || true
                break
            fi
            sleep 1
            wait_count=$((wait_count + 1))
        done
    done

    rm -f "$PID_FILE"
    echo "✅ 기존 서버를 중지했습니다."
}

start_ngrok_if_needed() {
    if [ "${RUN_NGROK:-0}" != "1" ]; then
        return
    fi

    require_command "ngrok" "brew install ngrok/ngrok/ngrok"
    echo "🌐 Starting ngrok in background..."
    ngrok http "$PORT" > /tmp/local-flutter-cicd-ngrok.log 2>&1 &
    echo "   Log: /tmp/local-flutter-cicd-ngrok.log"
}

start_foreground() {
    echo "🚀 Starting FastAPI server in foreground..."
    exec "$ROOT_DIR/venv/bin/uvicorn" src.main:app --host "$HOST" --port "$PORT"
}

start_background() {
    echo "🚀 Starting FastAPI server in background..."
    nohup "$ROOT_DIR/venv/bin/uvicorn" src.main:app --host "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1 </dev/null &
    local server_pid=$!
    echo "$server_pid" > "$PID_FILE"
    sleep 2

    if ! kill -0 "$server_pid" 2>/dev/null; then
        echo "❌ 서버 시작에 실패했습니다. 로그를 확인하세요: $LOG_FILE"
        exit 1
    fi

    echo "✅ 서버를 시작했습니다."
    echo "   PID: $server_pid"
    echo "   LOG: $LOG_FILE"
}

prepare_env

if [ "$BOOTSTRAP_ONLY" -eq 1 ]; then
    echo "✅ Bootstrap complete."
    exit 0
fi

cd "$ROOT_DIR"

if [ "$SYNC_MAIN" -eq 1 ]; then
    sync_main_branch
fi

stop_existing_server
start_ngrok_if_needed

if [ "$MODE" = "foreground" ]; then
    start_foreground
fi

start_background
