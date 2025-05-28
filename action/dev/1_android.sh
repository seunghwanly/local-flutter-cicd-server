#!/bin/bash
set -e

# 필수 환경변수 확인
DEV_LOCAL_DIR="${DEV_LOCAL_DIR:?DEV_LOCAL_DIR 환경변수가 필요합니다}"
DEV_FASTLANE_LANE="${DEV_FASTLANE_LANE:?DEV_FASTLANE_LANE 환경변수가 필요합니다}"
DEV_BRANCH_NAME="${DEV_BRANCH_NAME:-(알 수 없음)}"

echo "🚀 Android 배포 시작 (BRANCH: $DEV_BRANCH_NAME)"

cd $DEV_LOCAL_DIR/android

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
fastlane $DEV_FASTLANE_LANE build_name:"$BUILD_NAME" build_number:"$BUILD_NUMBER"

echo "✅ Android 빌드 완료"
