#!/bin/bash
# Flutter CI/CD - 격리된 Android 빌드 스크립트

set -e

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

# Fastlane 레인 결정 (환경변수 또는 기본값)
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

# Fastlane 명령 구성
FASTLANE_CMD="fvm exec fastlane $FASTLANE_LANE"

if [ ! -z "$BUILD_NAME" ] && [ ! -z "$BUILD_NUMBER" ]; then
    FASTLANE_CMD="$FASTLANE_CMD build_name:\"$BUILD_NAME\" build_number:\"$BUILD_NUMBER\""
elif [ ! -z "$BUILD_NAME" ]; then
    FASTLANE_CMD="$FASTLANE_CMD build_name:\"$BUILD_NAME\""
elif [ ! -z "$BUILD_NUMBER" ]; then
    FASTLANE_CMD="$FASTLANE_CMD build_number:\"$BUILD_NUMBER\""
fi

# Fastlane 실행
echo "🚀 Running: $FASTLANE_CMD"
if eval $FASTLANE_CMD; then
    echo "✅ Android 빌드 완료"
else
    echo "❌ Fastlane 빌드 실패 (exit code: $?)"
    exit 1
fi

