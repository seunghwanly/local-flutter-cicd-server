#!/bin/bash
set -e

# 필수 환경변수 확인
PROD_LOCAL_DIR="${PROD_LOCAL_DIR:?PROD_LOCAL_DIR 환경변수가 필요합니다}"
PROD_FASTLANE_LANE="${PROD_FASTLANE_LANE:?PROD_FASTLANE_LANE 환경변수가 필요합니다}"
PROD_BRANCH_NAME="${PROD_BRANCH_NAME:-(알 수 없음)}"

echo "🚀 iOS 배포 시작 (prod / BRANCH: $PROD_BRANCH_NAME)"

cd $PROD_LOCAL_DIR/ios

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
FASTLANE_CMD="fastlane $PROD_FASTLANE_LANE"

# 파라미터 추가 (순서 보장)
if [ ! -z "$BUILD_NAME" ] && [ ! -z "$BUILD_NUMBER" ]; then
    # 둘 다 있는 경우
    FASTLANE_CMD="$FASTLANE_CMD build_name:\"$BUILD_NAME\" build_number:\"$BUILD_NUMBER\""
elif [ ! -z "$BUILD_NAME" ]; then
    # build_name만 있는 경우
    FASTLANE_CMD="$FASTLANE_CMD build_name:\"$BUILD_NAME\""
elif [ ! -z "$BUILD_NUMBER" ]; then
    # build_number만 있는 경우
    FASTLANE_CMD="$FASTLANE_CMD build_number:\"$BUILD_NUMBER\""
fi

# fastlane 실행
echo "🚀 Running: $FASTLANE_CMD"
eval $FASTLANE_CMD

echo "✅ iOS 빌드 완료 (prod)"
