#!/bin/bash
set -e

# 필수 환경변수 확인
REPO_URL="${REPO_URL:?REPO_URL 환경변수가 필요합니다}"
DEV_BRANCH_NAME="${DEV_BRANCH_NAME:?DEV_BRANCH_NAME 환경변수가 필요합니다}"
DEV_LOCAL_DIR="${DEV_LOCAL_DIR:?DEV_LOCAL_DIR 환경변수가 필요합니다}"

echo "🚀 Deploying branch: $DEV_BRANCH_NAME"

# Git clone (최초 1회)
if [ ! -d "$DEV_LOCAL_DIR" ]; then
    echo "📦 Cloning repo..."
    git clone "$REPO_URL" "$DEV_LOCAL_DIR"
fi

# 해당 디렉토리로 이동
cd "$DEV_LOCAL_DIR" || exit 1

# 최신 상태로 만들기
echo "🔄 Fetching and checking out branch..."
git fetch origin

# Check if branch exists remotely
if git ls-remote --heads origin "$DEV_BRANCH_NAME" | grep -q "$DEV_BRANCH_NAME"; then
    echo "✅ Branch $DEV_BRANCH_NAME exists remotely"
    git checkout "$DEV_BRANCH_NAME" || git checkout -b "$DEV_BRANCH_NAME" "origin/$DEV_BRANCH_NAME"
    git stash
    git pull origin "$DEV_BRANCH_NAME"
else
    echo "❌ Error: Branch '$DEV_BRANCH_NAME' does not exist in the remote repository"
    echo "Available branches:"
    git branch -r | head -10
    exit 1
fi

# Flutter SDK가 이미 설정되어 있다고 가정
echo "🚧 Running flutter pub get ..."
flutter pub get

echo "✅ Setup success for branch: $DEV_BRANCH_NAME"
