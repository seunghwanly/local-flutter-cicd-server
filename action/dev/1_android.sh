#!/bin/bash
set -e

# 필수 환경변수 확인
DEV_LOCAL_DIR="${DEV_LOCAL_DIR:?DEV_LOCAL_DIR 환경변수가 필요합니다}"
DEV_FASTLANE_LANE="${DEV_FASTLANE_LANE:?DEV_FASTLANE_LANE 환경변수가 필요합니다}"
DEV_BRANCH_NAME="${DEV_BRANCH_NAME:-(알 수 없음)}"

echo "🚀 Android 배포 시작 (BRANCH: $DEV_BRANCH_NAME)"

cd "$DEV_LOCAL_DIR/android"
flutter pub get
fastlane "$DEV_FASTLANE_LANE"

echo "✅ Android 빌드 완료"
