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
export BUNDLE_PATH="${BUNDLE_PATH:-$GEM_HOME/bundle}"
export BUNDLE_DISABLE_SHARED_GEMS="${BUNDLE_DISABLE_SHARED_GEMS:-true}"

USE_BUNDLER=false
if [ -f "Gemfile" ]; then
    USE_BUNDLER=true
fi

echo "  ✅ 독립 환경 설정 완료"
echo "  📍 BUNDLE_PATH: $BUNDLE_PATH"
echo ""

# Fastlane 레인 결정
FASTLANE_LANE="${FASTLANE_LANE:-beta}"
BUILD_NAME="${BUILD_NAME:-}"
BUILD_NUMBER="${BUILD_NUMBER:-}"
COCOAPODS_VERSION="${COCOAPODS_VERSION:-}"
PATCH_MODE=false
if [[ "$FASTLANE_LANE" == patch_* ]]; then
    PATCH_MODE=true
fi
IOS_USE_BUNDLER="${IOS_USE_BUNDLER:-}"
if [ -z "$IOS_USE_BUNDLER" ]; then
    if [ "$PATCH_MODE" = true ]; then
        IOS_USE_BUNDLER=false
    elif [ "$USE_BUNDLER" = true ]; then
        IOS_USE_BUNDLER=true
    else
        IOS_USE_BUNDLER=false
    fi
fi
IOS_RUN_POD_INSTALL="${IOS_RUN_POD_INSTALL:-auto}"
SHOULD_RUN_POD_INSTALL=false
POD_INSTALL_REASONS=()

mark_pod_install_required() {
    SHOULD_RUN_POD_INSTALL=true
    POD_INSTALL_REASONS+=("$1")
}

ensure_flutter_ios_artifacts() {
    local project_root
    local artifact_path

    project_root="$(cd .. && pwd)"
    artifact_path="$project_root/.fvm/flutter_sdk/bin/cache/artifacts/engine/ios/Flutter.xcframework"

    if [ -d "$artifact_path" ]; then
        return
    fi

    echo "⚠️ Missing Flutter iOS engine artifact: $artifact_path"
    echo "📦 Running fvm flutter precache --ios before pod install"
    (
        cd "$project_root"
        fvm flutter precache --ios
    )
    mark_pod_install_required "Flutter iOS engine artifact was repaired via precache"
}

resolve_pod_state_file() {
    if [ -f "Pods/Manifest.lock" ]; then
        echo "Pods/Manifest.lock"
    elif [ -f "Podfile.lock" ]; then
        echo "Podfile.lock"
    else
        echo ""
    fi
}

evaluate_auto_pod_install() {
    local pod_state_file
    pod_state_file="$(resolve_pod_state_file)"

    if [ ! -f "Podfile.lock" ]; then
        mark_pod_install_required "Podfile.lock missing"
    fi
    if [ ! -d "Pods/Pods.xcodeproj" ]; then
        mark_pod_install_required "Pods/Pods.xcodeproj missing"
    fi
    if [ ! -d "Runner.xcworkspace" ]; then
        mark_pod_install_required "Runner.xcworkspace missing"
    fi
    if [ ! -f "Flutter/Generated.xcconfig" ]; then
        mark_pod_install_required "Flutter/Generated.xcconfig missing"
    fi
    if [ -f "Podfile.lock" ] && [ -f "Pods/Manifest.lock" ] && ! cmp -s "Podfile.lock" "Pods/Manifest.lock"; then
        mark_pod_install_required "Podfile.lock and Pods/Manifest.lock differ"
    fi
    if [ -n "$pod_state_file" ] && [ -f "Podfile" ] && [ "Podfile" -nt "$pod_state_file" ]; then
        mark_pod_install_required "Podfile is newer than $pod_state_file"
    fi
    if [ -f "../.flutter-plugins-dependencies" ] && { [ -z "$pod_state_file" ] || [ "../.flutter-plugins-dependencies" -nt "$pod_state_file" ]; }; then
        if [ -n "$pod_state_file" ]; then
            mark_pod_install_required ".flutter-plugins-dependencies is newer than $pod_state_file"
        else
            mark_pod_install_required ".flutter-plugins-dependencies changed without an existing pod state file"
        fi
    fi
    if [ "${IOS_FLUTTER_SDK_CHANGED:-false}" = "true" ]; then
        mark_pod_install_required "Flutter SDK version changed since previous sync"
    fi
}

case "$IOS_RUN_POD_INSTALL" in
    true|TRUE|1|yes|YES)
        mark_pod_install_required "forced by IOS_RUN_POD_INSTALL=$IOS_RUN_POD_INSTALL"
        ;;
    false|FALSE|0|no|NO)
        ;;
    auto|AUTO|"")
        evaluate_auto_pod_install
        ;;
    *)
        echo "⚠️ Unknown IOS_RUN_POD_INSTALL=$IOS_RUN_POD_INSTALL, falling back to auto detection"
        evaluate_auto_pod_install
        ;;
esac

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
elif [ "$IOS_USE_BUNDLER" = true ]; then
    echo "📦 Executing CocoaPods via: bundle exec pod"
    bundle exec pod --version
else
    echo "📦 Executing CocoaPods via: pod"
    pod --version
fi

ensure_flutter_ios_artifacts

# pod install 실행
if [ "$SHOULD_RUN_POD_INSTALL" = true ]; then
    echo "📚 Running pod install..."
    printf '  • %s\n' "${POD_INSTALL_REASONS[@]}"

    if [ -n "$COCOAPODS_VERSION" ]; then
        POD_INSTALL_CMD=(pod "_${COCOAPODS_VERSION}_" install)
    elif [ "$IOS_USE_BUNDLER" = true ]; then
        POD_INSTALL_CMD=(bundle exec pod install)
    else
        POD_INSTALL_CMD=(pod install)
    fi

    POD_INSTALL_LOG="$(mktemp)"
    if "${POD_INSTALL_CMD[@]}" >"$POD_INSTALL_LOG" 2>&1; then
        cat "$POD_INSTALL_LOG"
    else
        cat "$POD_INSTALL_LOG"
        if grep -Eiq "Unable to find a specification|could not find compatible versions|out-of-date source repos|Specs satisfying the" "$POD_INSTALL_LOG"; then
            echo "⚠️ pod install failed with a spec resolution error, retrying with --repo-update"
            "${POD_INSTALL_CMD[@]}" --repo-update
        else
            echo "❌ pod install failed without a repo update hint"
            rm -f "$POD_INSTALL_LOG"
            exit 1
        fi
    fi
    rm -f "$POD_INSTALL_LOG"
else
    echo "⏭️ Skipping pod install (IOS_RUN_POD_INSTALL=$IOS_RUN_POD_INSTALL, auto-detect found no changes)"
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

# Fastlane 실행 전 DerivedData 관련 환경변수 설정
export GYM_DERIVED_DATA_PATH="$DERIVED_DATA_PATH"
export GYM_XCARCHIVE_PATH="$DERIVED_DATA_PATH/Archives"

# Fastlane 실행
echo "🚀 Running: ${FASTLANE_CMD[*]}"
echo "📦 Using Bundler for Ruby tools: $IOS_USE_BUNDLER"
echo "📚 Run pod install: $SHOULD_RUN_POD_INSTALL"
echo "🏗️ Using DerivedData path: $DERIVED_DATA_PATH"
echo "🏗️ GYM_DERIVED_DATA_PATH: $GYM_DERIVED_DATA_PATH"
echo "🏗️ GYM_XCARCHIVE_PATH: $GYM_XCARCHIVE_PATH"
if "${FASTLANE_CMD[@]}"; then
    echo "✅ iOS 빌드 완료"
else
    echo "❌ Fastlane 빌드 실패 (exit code: $?)"
    exit 1
fi
