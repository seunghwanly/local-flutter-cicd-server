#!/bin/bash
set -e

# 필수 환경변수 확인
STAGE_LOCAL_DIR="${STAGE_LOCAL_DIR:?STAGE_LOCAL_DIR 환경변수가 필요합니다}"
STAGE_FASTLANE_LANE="${STAGE_FASTLANE_LANE:?STAGE_FASTLANE_LANE 환경변수가 필요합니다}"
STAGE_BRANCH_NAME="${STAGE_BRANCH_NAME:-(알 수 없음)}"

echo "🚀 Android 배포 시작 (stage / BRANCH: $STAGE_BRANCH_NAME)"

cd $STAGE_LOCAL_DIR/android

# 기본값 설정
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

# fastlane 명령어 구성
FASTLANE_CMD="fastlane $STAGE_FASTLANE_LANE"

# 파라미터 추가 (순서 보장)
if [ ! -z "$BUILD_NAME" ] && [ ! -z "$BUILD_NUMBER" ]; then
    FASTLANE_CMD="$FASTLANE_CMD build_name:\"$BUILD_NAME\" build_number:\"$BUILD_NUMBER\""
elif [ ! -z "$BUILD_NAME" ]; then
    FASTLANE_CMD="$FASTLANE_CMD build_name:\"$BUILD_NAME\""
elif [ ! -z "$BUILD_NUMBER" ]; then
    FASTLANE_CMD="$FASTLANE_CMD build_number:\"$BUILD_NUMBER\""
fi

# fastlane 실행
echo "🚀 Running: $FASTLANE_CMD"
eval $FASTLANE_CMD

echo "✅ Android 빌드 완료 (stage)"


