#!/bin/bash
set -e

# 필수 환경변수 확인
PROD_LOCAL_DIR="${PROD_LOCAL_DIR:?PROD_LOCAL_DIR 환경변수가 필요합니다}"
PROD_FASTLANE_LANE="${PROD_FASTLANE_LANE:?PROD_FASTLANE_LANE 환경변수가 필요합니다}"
PROD_BRANCH_NAME="${PROD_BRANCH_NAME:-(알 수 없음)}"

echo "🚀 iOS 배포 시작 (prod / BRANCH: $PROD_BRANCH_NAME)"

cd $PROD_LOCAL_DIR/ios

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
fastlane $PROD_FASTLANE_LANE build_name:"$BUILD_NAME" build_number:"$BUILD_NUMBER"

echo "✅ iOS 빌드 완료 (prod)"
