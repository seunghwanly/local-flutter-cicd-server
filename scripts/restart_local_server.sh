#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"

cd "$ROOT_DIR"

ensure_clean_worktree() {
    if [ -n "$(git status --porcelain)" ]; then
        echo "❌ 작업 트리가 깨끗하지 않습니다. 변경사항을 정리한 뒤 다시 시도하세요."
        git status --short
        exit 1
    fi
}

stop_existing_server() {
    local pids
    pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN || true)"

    if [ -z "$pids" ]; then
        echo "ℹ️ 포트 $PORT 에서 실행 중인 서버가 없습니다."
        return
    fi

    echo "🛑 포트 $PORT 에서 실행 중인 서버를 확인합니다..."

    for pid in $pids; do
        local command
        command="$(ps -p "$pid" -o command= 2>/dev/null || true)"

        if [[ "$command" != *"$ROOT_DIR"* && "$command" != *"uvicorn src.main:app"* && "$command" != *"local_run.sh"* ]]; then
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

    echo "✅ 기존 서버를 중지했습니다."
}

sync_main_branch() {
    echo "🔄 origin/main 최신 상태를 가져옵니다..."
    git fetch origin
    git checkout main
    git pull origin main
}

start_server() {
    echo "🚀 ./local_run.sh 로 서버를 다시 시작합니다..."
    exec ./local_run.sh
}

ensure_clean_worktree
stop_existing_server
sync_main_branch
start_server
