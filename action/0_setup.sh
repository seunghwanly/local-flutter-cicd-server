#!/bin/bash
# Flutter CI/CD - 격리된 Setup 스크립트
# 각 빌드는 완전히 독립된 환경에서 실행됩니다.

set -e

# ✅ 격리된 환경변수 확인
REPO_URL="${REPO_URL:?REPO_URL 환경변수가 필요합니다}"
BRANCH_NAME="${BRANCH_NAME:?BRANCH_NAME 환경변수가 필요합니다}"
LOCAL_DIR="${LOCAL_DIR:?LOCAL_DIR 환경변수가 필요합니다}"
PUB_CACHE="${PUB_CACHE:?PUB_CACHE 환경변수가 필요합니다}"

echo "🚀 Deploying branch: $BRANCH_NAME"
echo "📂 Repository directory: $LOCAL_DIR"
echo "🔒 PUB_CACHE: $PUB_CACHE"
echo "🔧 GRADLE_USER_HOME: ${GRADLE_USER_HOME:-default}"

# GITHUB_TOKEN이 있으면 HTTPS 모드, 없으면 SSH 모드
if [ ! -z "$GITHUB_TOKEN" ]; then
    echo "🔐 Using HTTPS authentication (GITHUB_TOKEN detected)"
    echo "   Skipping SSH checks - will use HTTPS for Git operations"
else
    # ✅ SSH 환경 진단
    echo "🔐 SSH Environment Diagnostics:"
    echo "   HOME: $HOME"
    echo "   SSH_AUTH_SOCK: ${SSH_AUTH_SOCK:-NOT SET}"
    echo "   GIT_SSH_COMMAND: ${GIT_SSH_COMMAND:-NOT SET}"

    # SSH 키 존재 확인
    if [ -f "$HOME/.ssh/id_rsa" ]; then
        echo "✅ SSH private key found"
        ls -l "$HOME/.ssh/id_rsa"
    else
        echo "❌ SSH private key NOT found at $HOME/.ssh/id_rsa"
        exit 1
    fi

    # SSH config 확인
    if [ -f "$HOME/.ssh/config" ]; then
        echo "✅ SSH config found"
        echo "   Config for github.com:"
        grep -A 3 "^Host github.com" "$HOME/.ssh/config" || echo "   (no specific config)"
    else
        echo "⚠️ SSH config not found (will use defaults)"
    fi

    # SSH Agent 확인
    if [ -n "$SSH_AUTH_SOCK" ] && [ -S "$SSH_AUTH_SOCK" ]; then
        echo "✅ SSH Agent is running"
        ssh-add -l 2>/dev/null || echo "   (no keys loaded, but agent is running)"
    else
        echo "⚠️ SSH Agent not detected"
        echo "   Attempting to start SSH Agent..."
        eval "$(ssh-agent -s)"
        ssh-add "$HOME/.ssh/id_rsa" 2>/dev/null || {
            echo "❌ Failed to add SSH key"
            echo "   Key might require a passphrase or is invalid"
            exit 1
        }
    fi

    # Git SSH 접근 테스트
    echo "🔍 Testing Git SSH access to GitHub..."
    ssh -T git@github.com 2>&1 | head -5 || {
        EXIT_CODE=$?
        if [ $EXIT_CODE -eq 1 ]; then
            # Exit code 1 is actually success for github.com SSH test
            echo "✅ SSH authentication to GitHub successful"
        else
            echo "❌ SSH authentication to GitHub failed (exit code: $EXIT_CODE)"
            echo "   This may cause git clone failures"
        fi
    }
fi

# Repository 접근 테스트
echo "🔍 Testing repository access..."
if git ls-remote "$REPO_URL" HEAD &>/dev/null; then
    echo "✅ Repository is accessible"
else
    echo "❌ Cannot access repository: $REPO_URL"
    echo "   Checking URL format..."
    echo "   URL: $REPO_URL"
    exit 1
fi

# Git clone (최초 1회)
if [ ! -d "$LOCAL_DIR/.git" ]; then
    echo "📦 Cloning repository..."
    git clone "$REPO_URL" "$LOCAL_DIR" || {
        echo "❌ Git clone failed"
        exit 1
    }
    echo "✅ Repository cloned"
else
    echo "✅ Repository already exists"
fi

# 해당 디렉토리로 이동
cd "$LOCAL_DIR" || exit 1

# 최신 상태로 만들기
echo "🔄 Fetching and checking out branch..."
git fetch origin

# 브랜치 존재 확인
if git ls-remote --heads origin "$BRANCH_NAME" | grep -q "$BRANCH_NAME"; then
    echo "✅ Branch $BRANCH_NAME exists remotely"
    git checkout "$BRANCH_NAME" || git checkout -b "$BRANCH_NAME" "origin/$BRANCH_NAME"
    # 기존 변경사항 제거 (이전 빌드 실패로 인한 잔존 파일 방지)
    git reset --hard "origin/$BRANCH_NAME"
    git clean -fdx
    git pull origin "$BRANCH_NAME"
else
    echo "❌ Error: Branch '$BRANCH_NAME' does not exist"
    echo "Available branches:"
    git branch -r | head -10
    exit 1
fi

# ✅ Git 인증 확인
echo "🔐 Checking Git credentials configuration..."

# Credential helper 확인
if git config --global --get credential.helper >/dev/null 2>&1; then
    echo "✅ Git credential helper configured: $(git config --global --get credential.helper)"
else
    echo "⚠️ No credential helper found, relying on environment setup"
fi

# .git-credentials 파일 확인
if [ -f "$HOME/.git-credentials" ] || [ ! -z "$GITHUB_TOKEN" ]; then
    echo "✅ Git HTTPS credentials available"
else
    echo "⚠️ No HTTPS credentials found (set GITHUB_TOKEN or configure .git-credentials)"
fi

# Flutter 버전 결정
echo "🚧 Resolving Flutter SDK version..."

# FLUTTER_SDK_VERSION이 제공되면 fvm use 실행, 없으면 .fvmrc 파일 사용
if [ ! -z "$FLUTTER_SDK_VERSION" ]; then
    echo "🔧 Using FLUTTER_SDK_VERSION from environment: $FLUTTER_SDK_VERSION"
    echo "📦 Running: fvm use $FLUTTER_SDK_VERSION"
    fvm use "$FLUTTER_SDK_VERSION" || {
        echo "❌ Failed to set Flutter SDK version: $FLUTTER_SDK_VERSION"
        exit 1
    }
    echo "✅ Flutter SDK version set to: $FLUTTER_SDK_VERSION"
else
    echo "📄 FLUTTER_SDK_VERSION not provided, using .fvmrc from repository"
    if [ -f ".fvmrc" ]; then
        echo "✅ Found .fvmrc file, FVM will use it automatically"
        # fvm use 명령어를 실행하지 않으면 FVM이 .fvmrc를 자동으로 사용합니다
    else
        echo "⚠️ Warning: .fvmrc file not found in repository"
        echo "   FVM will use the default Flutter version"
    fi
fi

# ✅ PUB_CACHE git 디렉토리 확인 (심볼릭 링크일 수 있음)
echo "📦 Checking PUB_CACHE git cache..."
if [ -L "$PUB_CACHE/git" ]; then
    echo "🔗 Git cache is symlinked to system cache"
    # 심볼릭 링크 유효성 검사
    if [ ! -e "$PUB_CACHE/git" ]; then
        echo "❌ Symlink is broken, removing..."
        rm -f "$PUB_CACHE/git"
        mkdir -p "$PUB_CACHE/git/cache"
    else
        echo "✅ Symlink is valid"
    fi
elif [ ! -d "$PUB_CACHE/git" ]; then
    echo "📂 Creating PUB_CACHE git directory..."
    mkdir -p "$PUB_CACHE/git/cache"
else
    echo "✅ PUB_CACHE git directory exists"
    
    # ✅ 손상된 git 캐시 정리 (심볼릭 링크가 아닌 경우만)
    echo "🧹 Checking for corrupted git caches in PUB_CACHE..."
    if [ -d "$PUB_CACHE/git/cache" ]; then
        corrupted_count=0
        for gitdir in "$PUB_CACHE/git/cache"/*; do
            if [ -d "$gitdir" ] && [ ! -L "$gitdir" ]; then
                # Git 디렉토리 유효성 검사
                if ! git -C "$gitdir" rev-parse --git-dir &>/dev/null; then
                    echo "🗑️ Removing corrupted cache: $(basename $gitdir)"
                    rm -rf "$gitdir"
                    corrupted_count=$((corrupted_count + 1))
                fi
            fi
        done
        
        if [ $corrupted_count -eq 0 ]; then
            echo "✅ No corrupted git caches found"
        else
            echo "🧹 Cleaned $corrupted_count corrupted git cache(s)"
        fi
    fi
fi

# ✅ 격리된 PUB_CACHE에 globally activate
echo "🚧 Installing global packages to isolated cache..."
echo "📍 PUB_CACHE bin will be at: $PUB_CACHE/bin"

# Melos globally activate (격리된 캐시에)
echo "🔧 Activating melos..."
fvm dart pub global activate melos

# FlutterFire CLI globally activate (격리된 캐시에)
echo "🔥 Activating flutterfire_cli..."
fvm dart pub global activate flutterfire_cli

# 의존성 설치 전 환경 재확인
echo "🚧 Running flutter pub get with verbose logging..."
echo "🔍 Pre-pub-get environment check:"
echo "   PUB_CACHE (absolute): $(cd "$PUB_CACHE" && pwd)"
echo "   Current directory: $(pwd)"
echo "   SSH_AUTH_SOCK: ${SSH_AUTH_SOCK:-NOT SET}"
echo "   GIT_SSH_COMMAND: ${GIT_SSH_COMMAND:-NOT SET}"

# Note: flutter clean은 불필요 (격리된 환경 + git clean -fdx로 이미 깨끗함)

# pubspec.yaml에서 git 의존성 확인
if grep -q "git:" pubspec.yaml 2>/dev/null; then
    echo "📋 Git dependencies found in pubspec.yaml:"
    grep -A 3 "git:" pubspec.yaml | head -20
    echo ""
fi

# 첫 번째 시도 (verbose mode)
echo "🔄 Attempting pub get (verbose)..."
if fvm exec melos run pub 2>&1; then
    echo "✅ Melos pub get succeeded"
elif fvm flutter pub get --verbose 2>&1; then
    echo "✅ Flutter pub get succeeded"
else
    echo "❌ First pub get attempt failed"
    
    # Git 의존성 접근 테스트
    if grep -q "git:" pubspec.yaml 2>/dev/null; then
        echo "🔍 Testing Git repository access..."
        grep -oP 'url:\s*\K[^\s]+' pubspec.yaml 2>/dev/null | while read url; do
            echo "  Testing: $url"
            if git ls-remote "$url" HEAD &>/dev/null; then
                echo "    ✅ Access OK"
            else
                echo "    ❌ Access FAILED - Check credentials"
            fi
        done
    fi
    
    # Git 캐시 재생성 시도
    echo "⚠️ Attempting to clean and rebuild git cache..."
    
    # 심볼릭 링크인 경우 제거하고 새로 시작
    if [ -L "$PUB_CACHE/git" ]; then
        echo "🔗 Removing symlinked git cache..."
        rm -f "$PUB_CACHE/git"
        mkdir -p "$PUB_CACHE/git/cache"
    else
        # 일반 디렉토리인 경우 손상된 캐시만 제거
        echo "🧹 Removing all git caches..."
        rm -rf "$PUB_CACHE/git/cache"/*
    fi
    
    # 캐시 복구
    echo "🔧 Running pub cache repair..."
    fvm flutter pub cache repair
    
    # 재시도
    echo "🔄 Retrying pub get after cache cleanup..."
    if fvm exec melos run pub 2>&1; then
        echo "✅ Melos pub get succeeded after cache cleanup"
    elif fvm flutter pub get --verbose 2>&1; then
        echo "✅ Flutter pub get succeeded after cache cleanup"
    else
        echo "❌ Pub get failed even after cache cleanup"
        echo ""
        echo "💡 Troubleshooting tips:"
        echo "   1. SSH authentication: ssh -T git@github.com"
        echo "   2. Git dependencies access: Check if private repos are accessible"
        echo "   3. SSH_AUTH_SOCK: ${SSH_AUTH_SOCK:-NOT SET}"
        echo "   4. GIT_SSH_COMMAND: ${GIT_SSH_COMMAND:-NOT SET}"
        exit 1
    fi
fi

echo "✅ Setup success for branch: $BRANCH_NAME"
echo "✅ Global packages installed to: $PUB_CACHE/global_packages"