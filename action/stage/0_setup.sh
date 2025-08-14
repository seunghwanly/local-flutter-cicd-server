#!/bin/bash
set -e

# 필수 환경변수 확인
REPO_URL="${REPO_URL:?REPO_URL 환경변수가 필요합니다}"
STAGE_BRANCH_NAME="${STAGE_BRANCH_NAME:?STAGE_BRANCH_NAME 환경변수가 필요합니다}"
STAGE_LOCAL_DIR="${STAGE_LOCAL_DIR:?STAGE_LOCAL_DIR 환경변수가 필요합니다}"

echo "🚀 Deploying branch: $STAGE_BRANCH_NAME (stage)"

# Git clone (최초 1회)
if [ ! -d "$STAGE_LOCAL_DIR" ]; then
    echo "📦 Cloning repo..."
    git clone "$REPO_URL" "$STAGE_LOCAL_DIR"
fi

# 해당 디렉토리로 이동
cd "$STAGE_LOCAL_DIR" || exit 1

# 최신 상태로 만들기
echo "🔄 Fetching and checking out branch..."
git fetch origin

# Check if branch exists remotely
if git ls-remote --heads origin "$STAGE_BRANCH_NAME" | grep -q "$STAGE_BRANCH_NAME"; then
    echo "✅ Branch $STAGE_BRANCH_NAME exists remotely"
    git checkout "$STAGE_BRANCH_NAME" || git checkout -b "$STAGE_BRANCH_NAME" "origin/$STAGE_BRANCH_NAME"
    git stash
    git pull origin "$STAGE_BRANCH_NAME"
else
    echo "❌ Error: Branch '$STAGE_BRANCH_NAME' does not exist in the remote repository"
    echo "Available branches:"
    git branch -r | head -10
    exit 1
fi

# Flutter SDK가 이미 설정되어 있다고 가정
echo "🚧 Running flutter pub get ..."
flutter pub get

echo "✅ Setup success for branch: $STAGE_BRANCH_NAME (stage)"


