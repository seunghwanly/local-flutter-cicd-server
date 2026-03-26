#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"
RUNTIME_DIR="$ROOT_DIR/.workspace/runtime"
PID_FILE="$RUNTIME_DIR/server.pid"

stop_repo_server() {
    local pids
    pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN || true)"

    if [ -z "$pids" ]; then
        echo "ℹ️ 포트 $PORT 에서 실행 중인 서버가 없습니다."
        return
    fi

    echo "🛑 포트 $PORT 에서 실행 중인 서버를 종료합니다..."
    for pid in $pids; do
        local command
        command="$(ps -p "$pid" -o command= 2>/dev/null || true)"

        if [[ "$command" != *"$ROOT_DIR"* && "$command" != *"uvicorn src.main:app"* && "$command" != *"scripts/start.sh"* ]]; then
            echo "❌ 포트 $PORT 를 사용 중인 프로세스가 이 저장소의 서버로 보이지 않습니다."
            echo "   PID: $pid"
            echo "   CMD: $command"
            exit 1
        fi

        kill "$pid"
    done
}

clean_runtime() {
    echo "🧹 런타임 산출물을 정리합니다..."
    rm -f "$PID_FILE"
    rm -rf "$RUNTIME_DIR"
    find "$ROOT_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} +
}

stop_repo_server
clean_runtime
echo "✅ Clean complete."
