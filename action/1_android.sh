#!/bin/bash
# Flutter CI/CD - 격리된 Android 빌드 스크립트

set -euo pipefail

# ✅ 격리된 환경변수 확인
LOCAL_DIR="${LOCAL_DIR:?LOCAL_DIR 환경변수가 필요합니다}"
GRADLE_USER_HOME="${GRADLE_USER_HOME:?GRADLE_USER_HOME 환경변수가 필요합니다}"
PUB_CACHE="${PUB_CACHE:?PUB_CACHE 환경변수가 필요합니다}"
GEM_HOME="${GEM_HOME:?GEM_HOME 환경변수가 필요합니다}"

echo "🚀 Android 배포 시작"
echo "📂 Repository: $LOCAL_DIR"
echo "🔧 Gradle Home: $GRADLE_USER_HOME"
echo "🔒 PUB_CACHE: $PUB_CACHE"
echo "💎 GEM_HOME: $GEM_HOME"

cd "$LOCAL_DIR/android" || exit 1

# 독립적인 환경 확인
echo ""
echo "🔍 환경 독립성 검증..."
echo "  📍 GEM_HOME: $GEM_HOME"
echo "  📍 GEM_PATH: $GEM_HOME"

# PATH에 GEM_HOME/bin 추가 (독립 gem 사용)
export PATH="$GEM_HOME/bin:$PATH"
export GEM_PATH="$GEM_HOME"

USE_BUNDLER=false
if [ -f "Gemfile" ]; then
    USE_BUNDLER=true
fi
if [[ "${FASTLANE_LANE:-beta}" == patch_* ]]; then
    echo "❌ Shorebird patch is only supported for iOS in this pipeline"
    exit 1
fi

echo "  ✅ 독립 환경 설정 완료"
echo ""

if [ "$USE_BUNDLER" = true ]; then
    echo "📦 Gemfile detected, using Bundler prepared by Python setup"
else
    echo "📦 Using gem-based tooling prepared by Python setup"
    if ! gem list -i digest-crc -v "~> 0.4" > /dev/null 2>&1; then
        echo "❌ digest-crc is not installed. Python setup should prepare it before this script runs."
        exit 1
    fi
    if ! gem list -i fastlane > /dev/null 2>&1; then
        echo "❌ Fastlane is not installed. Python setup should prepare it before this script runs."
        exit 1
    fi
fi

# Fastlane 레인 결정 (환경변수 또는 기본값)
FASTLANE_LANE="${FASTLANE_LANE:-beta}"
BUILD_NAME="${BUILD_NAME:-}"
BUILD_NUMBER="${BUILD_NUMBER:-}"

# Fastlane 명령 구성
if [ "$USE_BUNDLER" = true ]; then
    FASTLANE_CMD=(bundle exec fastlane "$FASTLANE_LANE")
else
    FASTLANE_CMD=(fvm exec fastlane "$FASTLANE_LANE")
fi

if [ -n "$BUILD_NAME" ] && [ -n "$BUILD_NUMBER" ]; then
    FASTLANE_CMD+=("build_name:$BUILD_NAME" "build_number:$BUILD_NUMBER")
elif [ -n "$BUILD_NAME" ]; then
    FASTLANE_CMD+=("build_name:$BUILD_NAME")
elif [ -n "$BUILD_NUMBER" ]; then
    FASTLANE_CMD+=("build_number:$BUILD_NUMBER")
fi

# Fastlane 실행
echo "🚀 Running: ${FASTLANE_CMD[*]}"
if "${FASTLANE_CMD[@]}"; then
    echo "✅ Android 빌드 완료"
else
    echo "❌ Fastlane 빌드 실패 (exit code: $?)"
    exit 1
fi
