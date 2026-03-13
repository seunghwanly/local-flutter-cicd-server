#!/bin/bash
# Flutter CI/CD - 격리된 iOS 빌드 스크립트

set -euo pipefail

# ✅ 격리된 환경변수 확인
LOCAL_DIR="${LOCAL_DIR:?LOCAL_DIR 환경변수가 필요합니다}"
PUB_CACHE="${PUB_CACHE:?PUB_CACHE 환경변수가 필요합니다}"
GEM_HOME="${GEM_HOME:?GEM_HOME 환경변수가 필요합니다}"
CP_HOME_DIR="${CP_HOME_DIR:?CP_HOME_DIR 환경변수가 필요합니다}"
DERIVED_DATA_PATH="${DERIVED_DATA_PATH:?DERIVED_DATA_PATH 환경변수가 필요합니다}"

echo "🚀 iOS 배포 시작"
echo "📂 Repository: $LOCAL_DIR"
echo "🔒 PUB_CACHE: $PUB_CACHE"
echo "💎 GEM_HOME: $GEM_HOME"
echo "🍫 CP_HOME_DIR: $CP_HOME_DIR"
echo "🏗️ DERIVED_DATA_PATH: $DERIVED_DATA_PATH"

# iOS 디렉토리로 이동
cd "$LOCAL_DIR/ios" || exit 1
echo "✅ 현재 디렉토리: $(pwd)"

# 독립적인 환경 확인
echo ""
echo "🔍 환경 독립성 검증..."
echo "  📍 GEM_HOME: $GEM_HOME"
echo "  📍 GEM_PATH: $GEM_HOME"
echo "  📍 CP_HOME_DIR: $CP_HOME_DIR"
echo "  📍 DERIVED_DATA_PATH: $DERIVED_DATA_PATH"

# CocoaPods가 독립 캐시를 사용하는지 확인
export CP_HOME_DIR="$CP_HOME_DIR"

# DerivedData 경로 설정
export DERIVED_DATA_PATH="$DERIVED_DATA_PATH"

# Flutter 빌드 시 DerivedData 경로를 사용하도록 환경변수 설정
export FLUTTER_BUILD_DERIVED_DATA_PATH="$DERIVED_DATA_PATH"

# PATH에 GEM_HOME/bin 추가 (독립 gem 사용)
export PATH="$GEM_HOME/bin:$PATH"
export GEM_PATH="$GEM_HOME"

USE_BUNDLER=false
if [ -f "Gemfile" ]; then
    USE_BUNDLER=true
fi

echo "  ✅ 독립 환경 설정 완료"
echo ""

# Fastlane 레인 결정
FASTLANE_LANE="${FASTLANE_LANE:-beta}"
BUILD_NAME="${BUILD_NAME:-}"
BUILD_NUMBER="${BUILD_NUMBER:-}"
COCOAPODS_VERSION="${COCOAPODS_VERSION:-}"

# # Flutter 아티팩트 준비
# echo "📦 Ensuring flutter artifacts..."
# pushd .. > /dev/null
# # iOS 네이티브 프로젝트 설정 파일 생성 (필수)
# fvm flutter --suppress-analytics --no-version-check build ios --config-only || true
# popd > /dev/null

if [ "$USE_BUNDLER" = true ]; then
    echo "📦 Gemfile detected, using Bundler prepared by Python setup"
    if [ -f "Gemfile.lock" ]; then
        LOCKED_COCOAPODS_VERSION="$(ruby -e 'lock = File.read("Gemfile.lock"); match = lock.match(/^ {4}cocoapods \(([^)]+)\)$/); puts(match ? match[1] : "")')"
        if [ -n "$LOCKED_COCOAPODS_VERSION" ]; then
            echo "📦 Gemfile.lock CocoaPods version: $LOCKED_COCOAPODS_VERSION"
        else
            echo "⚠️ Gemfile.lock exists but CocoaPods version could not be parsed"
        fi
    else
        echo "⚠️ Gemfile detected without Gemfile.lock"
    fi
else
    echo "📦 Using gem-based tooling prepared by Python setup"
    if ! gem list -i cocoapods > /dev/null 2>&1; then
        echo "❌ CocoaPods is not installed. Python setup should prepare it before this script runs."
        exit 1
    fi
    if ! gem list -i fastlane > /dev/null 2>&1; then
        echo "❌ Fastlane is not installed. Python setup should prepare it before this script runs."
        exit 1
    fi
fi

# CocoaPods 버전 확인
echo "📦 CocoaPods version:"
if [ -n "$COCOAPODS_VERSION" ]; then
    echo "📦 Executing CocoaPods via: pod _${COCOAPODS_VERSION}_"
    pod "_${COCOAPODS_VERSION}_" --version
elif [ "$USE_BUNDLER" = true ]; then
    echo "📦 Executing CocoaPods via: bundle exec pod"
    bundle exec pod --version
else
    echo "📦 Executing CocoaPods via: pod"
    pod --version
fi

# pod install 실행
echo "📚 Running pod install..."
if [ -n "$COCOAPODS_VERSION" ]; then
    if pod "_${COCOAPODS_VERSION}_" install; then
        true
    else
        echo "⚠️ pod install failed, retrying with --repo-update"
        pod "_${COCOAPODS_VERSION}_" install --repo-update
    fi
elif [ "$USE_BUNDLER" = true ]; then
    if bundle exec pod install; then
        true
    else
        echo "⚠️ pod install failed, retrying with --repo-update"
        bundle exec pod install --repo-update
    fi
else
    if pod install; then
        true
    else
        echo "⚠️ pod install failed, retrying with --repo-update"
        pod install --repo-update
    fi
fi

# # Fastlane match (필요시)
# # Flavor에 따라 match 타입 결정
# MATCH_TYPE="appstore"
# if [ "$FLAVOR" = "dev" ]; then
#     MATCH_TYPE="development"
# fi

# echo "🔑 Running fastlane match ($MATCH_TYPE)..."
# if ! fvm exec fastlane match $MATCH_TYPE --readonly; then
#     echo "⚠️ Fastlane match failed, but continuing (might be optional)"
# fi

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

# Fastlane 실행 전 DerivedData 관련 환경변수 설정
export GYM_DERIVED_DATA_PATH="$DERIVED_DATA_PATH"
export GYM_XCARCHIVE_PATH="$DERIVED_DATA_PATH/Archives"

# Fastlane 실행
echo "🚀 Running: ${FASTLANE_CMD[*]}"
echo "🏗️ Using DerivedData path: $DERIVED_DATA_PATH"
echo "🏗️ GYM_DERIVED_DATA_PATH: $GYM_DERIVED_DATA_PATH"
echo "🏗️ GYM_XCARCHIVE_PATH: $GYM_XCARCHIVE_PATH"
if "${FASTLANE_CMD[@]}"; then
    echo "✅ iOS 빌드 완료"
else
    echo "❌ Fastlane 빌드 실패 (exit code: $?)"
    exit 1
fi
