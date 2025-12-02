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

# 독립적인 환경 확인
echo ""
echo "🔍 환경 독립성 검증..."
echo "  📍 GEM_HOME: $GEM_HOME"
echo "  📍 GEM_PATH: $GEM_HOME"

# PATH에 GEM_HOME/bin 추가 (독립 gem 사용)
export PATH="$GEM_HOME/bin:$PATH"
export GEM_PATH="$GEM_HOME"

echo "  ✅ 독립 환경 설정 완료"
echo ""

# gem 의존성 문제 해결: digest-crc 버전 충돌 방지
echo "🔧 Resolving gem dependencies..."
# google-cloud-storage가 요구하는 digest-crc (~> 0.4) 버전 확인 및 설치
DIGEST_CRC_LIST=$(gem list digest-crc 2>/dev/null || echo "")
if [ ! -z "$DIGEST_CRC_LIST" ]; then
    # 설치된 버전 추출 (macOS 호환)
    DIGEST_CRC_VERSIONS=$(echo "$DIGEST_CRC_LIST" | sed -n 's/.*digest-crc (\(.*\))/\1/p' | tr -d '()')
    if [ ! -z "$DIGEST_CRC_VERSIONS" ]; then
        echo "  📦 Current digest-crc versions: $DIGEST_CRC_VERSIONS"
        # 0.4.x 버전이 있는지 확인
        HAS_04_VERSION=false
        for version in $DIGEST_CRC_VERSIONS; do
            if [[ "$version" =~ ^0\.4\. ]]; then
                HAS_04_VERSION=true
                break
            fi
        done
        
        # 0.4.x 버전이 없고 다른 버전이 있으면 제거
        if [ "$HAS_04_VERSION" = false ]; then
            echo "  🔄 Removing incompatible digest-crc versions..."
            for version in $DIGEST_CRC_VERSIONS; do
                gem uninstall digest-crc -v "$version" -x -I || true
            done
        fi
    fi
fi

# 올바른 버전의 digest-crc 설치
if ! gem list -i digest-crc -v "~> 0.4" > /dev/null 2>&1; then
    echo "💎 Installing digest-crc ~> 0.4..."
    # 0.4.x 버전 중 최신 버전 설치 시도
    gem install -N digest-crc -v "~> 0.4" || {
        echo "⚠️ Failed to install digest-crc ~> 0.4, trying specific version 0.6.1..."
        gem install -N digest-crc -v "0.6.1" || {
            echo "⚠️ Trying version 0.5.1..."
            gem install -N digest-crc -v "0.5.1" || true
        }
    }
    echo "✅ digest-crc installed"
else
    echo "✅ digest-crc already installed with correct version"
fi

# Fastlane 설치 (격리된 GEM_HOME에 설치)
echo "🚀 Installing Fastlane in isolated GEM_HOME..."
if [ ! -z "$FASTLANE_VERSION" ]; then
    echo "💎 Installing Fastlane $FASTLANE_VERSION..."
    if ! gem list -i fastlane -v "$FASTLANE_VERSION" > /dev/null 2>&1; then
        gem install -N fastlane -v "$FASTLANE_VERSION" || {
            echo "⚠️ Fastlane installation failed, attempting dependency resolution..."
            # 의존성 문제 해결 시도
            gem install -N digest-crc -v "~> 0.4" || gem install -N digest-crc -v "0.6.1" || true
            gem install -N fastlane -v "$FASTLANE_VERSION"
        }
        echo "✅ Fastlane $FASTLANE_VERSION installed"
    else
        echo "✅ Fastlane $FASTLANE_VERSION already installed"
    fi
else
    echo "💎 Installing latest Fastlane..."
    if ! gem list -i fastlane > /dev/null 2>&1; then
        gem install -N fastlane || {
            echo "⚠️ Fastlane installation failed, attempting dependency resolution..."
            # 의존성 문제 해결 시도
            gem install -N digest-crc -v "~> 0.4" || gem install -N digest-crc -v "0.6.1" || true
            gem install -N fastlane
        }
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

