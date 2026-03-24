#!/bin/bash
# Flutter CI/CD - 격리된 iOS 빌드 스크립트

set -euo pipefail

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

cd "$LOCAL_DIR/ios" || exit 1
echo "✅ 현재 디렉토리: $(pwd)"

export CP_HOME_DIR="$CP_HOME_DIR"
export DERIVED_DATA_PATH="$DERIVED_DATA_PATH"
export FLUTTER_BUILD_DERIVED_DATA_PATH="$DERIVED_DATA_PATH"
export PATH="$GEM_HOME/bin:$PATH"
export GEM_PATH="$GEM_HOME"
export BUNDLE_PATH="${BUNDLE_PATH:-$GEM_HOME/bundle}"
export BUNDLE_DISABLE_SHARED_GEMS="${BUNDLE_DISABLE_SHARED_GEMS:-true}"

IOS_USE_BUNDLER="${IOS_USE_BUNDLER:-false}"
IOS_SHOULD_RUN_POD_INSTALL="${IOS_SHOULD_RUN_POD_INSTALL:-${IOS_RUN_POD_INSTALL:-false}}"
FASTLANE_LANE="${FASTLANE_LANE:-beta}"
BUILD_NAME="${BUILD_NAME:-}"
BUILD_NUMBER="${BUILD_NUMBER:-}"
COCOAPODS_VERSION="${COCOAPODS_VERSION:-}"
PATCH_MODE=false

if [[ "$FASTLANE_LANE" == patch_* ]]; then
    PATCH_MODE=true
fi

echo ""
echo "🔍 Python 준비 입력 소비..."
echo "  📍 IOS_USE_BUNDLER: $IOS_USE_BUNDLER"
echo "  📍 IOS_SHOULD_RUN_POD_INSTALL: $IOS_SHOULD_RUN_POD_INSTALL"
echo "  📍 BUNDLE_PATH: $BUNDLE_PATH"
echo ""

if [ "$IOS_USE_BUNDLER" = true ]; then
    echo "📦 Using Bundler prepared by Python setup"
else
    echo "📦 Using gem-based tooling prepared by Python setup"
fi

echo "📦 CocoaPods version:"
if [ -n "$COCOAPODS_VERSION" ]; then
    echo "📦 Executing CocoaPods via: pod _${COCOAPODS_VERSION}_"
    pod "_${COCOAPODS_VERSION}_" --version
elif [ "$IOS_USE_BUNDLER" = true ]; then
    echo "📦 Executing CocoaPods via: bundle exec pod"
    bundle exec pod --version
else
    echo "📦 Executing CocoaPods via: pod"
    pod --version
fi

if [ "$IOS_SHOULD_RUN_POD_INSTALL" = true ]; then
    echo "📚 Running pod install..."
    if [ -n "${IOS_POD_INSTALL_REASONS:-}" ]; then
        echo "  • $IOS_POD_INSTALL_REASONS"
    fi
    if [ -n "$COCOAPODS_VERSION" ]; then
        POD_INSTALL_CMD=(pod "_${COCOAPODS_VERSION}_" install)
    elif [ "$IOS_USE_BUNDLER" = true ]; then
        POD_INSTALL_CMD=(bundle exec pod install)
    else
        POD_INSTALL_CMD=(pod install)
    fi

    "${POD_INSTALL_CMD[@]}"
else
    echo "⏭️ Skipping pod install (IOS_SHOULD_RUN_POD_INSTALL=$IOS_SHOULD_RUN_POD_INSTALL)"
fi

if [ "$IOS_USE_BUNDLER" = true ]; then
    FASTLANE_CMD=(bundle exec fastlane "$FASTLANE_LANE")
else
    FASTLANE_CMD=(fvm exec fastlane "$FASTLANE_LANE")
fi

if [ "$PATCH_MODE" = true ]; then
    if [ -z "$BUILD_NAME" ]; then
        echo "❌ Shorebird patch requires BUILD_NAME as release_version"
        exit 1
    fi

    echo "🐦 Shorebird patch mode detected"
    echo "  • flavor: $FLAVOR"
    echo "  • branch_name: ${BRANCH_NAME:-unknown}"
    echo "  • release_version: $BUILD_NAME"
    echo "  • platform: ios"
    echo "  • lane: $FASTLANE_LANE"
    if [ -n "$BUILD_NUMBER" ]; then
        echo "ℹ️ patch_number=$BUILD_NUMBER (현재 로그/상태 추적용으로만 유지)"
    fi

    FASTLANE_CMD+=("flavor:$FLAVOR" "release_version:$BUILD_NAME" "branch_name:${BRANCH_NAME:-}")
    if [ -n "$BUILD_NUMBER" ]; then
        FASTLANE_CMD+=("patch_number:$BUILD_NUMBER")
    fi
else
    if [ -n "$BUILD_NAME" ] && [ -n "$BUILD_NUMBER" ]; then
        FASTLANE_CMD+=("build_name:$BUILD_NAME" "build_number:$BUILD_NUMBER")
    elif [ -n "$BUILD_NAME" ]; then
        FASTLANE_CMD+=("build_name:$BUILD_NAME")
    elif [ -n "$BUILD_NUMBER" ]; then
        FASTLANE_CMD+=("build_number:$BUILD_NUMBER")
    fi
fi

export GYM_DERIVED_DATA_PATH="$DERIVED_DATA_PATH"
export GYM_XCARCHIVE_PATH="$DERIVED_DATA_PATH/Archives"

echo "🚀 Running: ${FASTLANE_CMD[*]}"
echo "📦 Using Bundler for Ruby tools: $IOS_USE_BUNDLER"
echo "📚 Run pod install: $IOS_SHOULD_RUN_POD_INSTALL"
echo "🏗️ Using DerivedData path: $DERIVED_DATA_PATH"
echo "🏗️ GYM_DERIVED_DATA_PATH: $GYM_DERIVED_DATA_PATH"
echo "🏗️ GYM_XCARCHIVE_PATH: $GYM_XCARCHIVE_PATH"
if "${FASTLANE_CMD[@]}"; then
    echo "✅ iOS 빌드 완료"
else
    echo "❌ Fastlane 빌드 실패 (exit code: $?)"
    exit 1
fi
