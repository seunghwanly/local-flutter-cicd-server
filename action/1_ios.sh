#!/bin/bash
# Flutter CI/CD - 격리된 iOS 빌드 스크립트

set -e

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

echo "  ✅ 독립 환경 설정 완료"
echo ""

# Fastlane 레인 결정
FASTLANE_LANE="${FASTLANE_LANE:-beta}"

# 빌드 파라미터 처리
BUILD_NAME=""
BUILD_NUMBER=""

while getopts n:b: opt; do
    case $opt in
    n)
        echo "✅ build_name set: $OPTARG"
        BUILD_NAME=$(echo "$OPTARG" | xargs)
        ;;
    b)
        echo "✅ build_number set: $OPTARG"
        BUILD_NUMBER=$(echo "$OPTARG" | xargs)
        ;;
    *)
        echo "Invalid option: -$opt"
        exit 1
        ;;
    esac
done

# # Flutter 아티팩트 준비
# echo "📦 Ensuring flutter artifacts..."
# pushd .. > /dev/null
# # iOS 네이티브 프로젝트 설정 파일 생성 (필수)
# fvm flutter --suppress-analytics --no-version-check build ios --config-only || true
# popd > /dev/null

# CocoaPods 설치 (격리된 GEM_HOME에 버전별로 설치) - Fastlane보다 먼저 설치
if [ ! -z "$COCOAPODS_VERSION" ]; then
    echo "💎 Installing CocoaPods $COCOAPODS_VERSION in isolated GEM_HOME..."
    if ! gem list -i cocoapods -v "$COCOAPODS_VERSION" > /dev/null 2>&1; then
        gem install -N cocoapods -v "$COCOAPODS_VERSION"
        echo "✅ CocoaPods $COCOAPODS_VERSION installed"
    else
        echo "✅ CocoaPods $COCOAPODS_VERSION already installed"
    fi
else
    echo "⚠️ COCOAPODS_VERSION not specified, installing latest CocoaPods"
    if ! gem list -i cocoapods > /dev/null 2>&1; then
        gem install -N cocoapods
        echo "✅ CocoaPods installed"
    else
        echo "✅ CocoaPods already installed"
    fi
fi

# Fastlane 설치 (격리된 GEM_HOME에 설치)
echo "🚀 Installing Fastlane in isolated GEM_HOME..."
if [ ! -z "$FASTLANE_VERSION" ]; then
    echo "💎 Installing Fastlane $FASTLANE_VERSION..."
    if ! gem list -i fastlane -v "$FASTLANE_VERSION" > /dev/null 2>&1; then
        gem install -N fastlane -v "$FASTLANE_VERSION"
        echo "✅ Fastlane $FASTLANE_VERSION installed"
    else
        echo "✅ Fastlane $FASTLANE_VERSION already installed"
    fi
else
    echo "💎 Installing latest Fastlane..."
    if ! gem list -i fastlane > /dev/null 2>&1; then
        gem install -N fastlane
        echo "✅ Fastlane installed"
    else
        echo "✅ Fastlane already installed"
    fi
fi

# Fastlane 설치 확인
if ! gem list -i fastlane > /dev/null 2>&1; then
    echo "❌ Fastlane installation failed"
    exit 1
fi

# Fastlane 플러그인 설치 (Pluginfile이 있는 경우)
if [ -f "fastlane/Pluginfile" ]; then
    echo "🔌 Installing Fastlane plugins from Pluginfile..."
    
    # Pluginfile에서 플러그인 추출 및 설치
    while IFS= read -r line; do
        # gem 'fastlane-plugin-xxx' 형태의 라인 파싱
        if [[ $line =~ gem[[:space:]]+[\'\"](fastlane-plugin-[^\'\"]+)[\'\"] ]]; then
            plugin_name="${BASH_REMATCH[1]}"
            echo "  📦 Installing $plugin_name..."
            if ! gem list -i "$plugin_name" > /dev/null 2>&1; then
                gem install -N "$plugin_name"
                echo "  ✅ $plugin_name installed"
            else
                echo "  ✅ $plugin_name already installed"
            fi
        fi
    done < "fastlane/Pluginfile"
else
    echo "⚠️ No Pluginfile found, skipping plugin installation"
fi

# CocoaPods 버전 확인
echo "📦 CocoaPods version:"
pod --version

# pod install 실행
echo "📚 Running pod install..."
pod install --repo-update

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
FASTLANE_CMD="fvm exec fastlane $FASTLANE_LANE"

if [ ! -z "$BUILD_NAME" ] && [ ! -z "$BUILD_NUMBER" ]; then
    FASTLANE_CMD="$FASTLANE_CMD build_name:\"$BUILD_NAME\" build_number:\"$BUILD_NUMBER\""
elif [ ! -z "$BUILD_NAME" ]; then
    FASTLANE_CMD="$FASTLANE_CMD build_name:\"$BUILD_NAME\""
elif [ ! -z "$BUILD_NUMBER" ]; then
    FASTLANE_CMD="$FASTLANE_CMD build_number:\"$BUILD_NUMBER\""
fi

# Fastlane 실행 전 DerivedData 관련 환경변수 설정
export GYM_DERIVED_DATA_PATH="$DERIVED_DATA_PATH"
export GYM_XCARCHIVE_PATH="$DERIVED_DATA_PATH/Archives"

# Fastlane 실행
echo "🚀 Running: $FASTLANE_CMD"
echo "🏗️ Using DerivedData path: $DERIVED_DATA_PATH"
echo "🏗️ GYM_DERIVED_DATA_PATH: $GYM_DERIVED_DATA_PATH"
echo "🏗️ GYM_XCARCHIVE_PATH: $GYM_XCARCHIVE_PATH"
if eval $FASTLANE_CMD; then
    echo "✅ iOS 빌드 완료"
else
    echo "❌ Fastlane 빌드 실패 (exit code: $?)"
    exit 1
fi

