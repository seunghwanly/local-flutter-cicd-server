## 우선순위 기반 설계 (FVM/Pods 버전 분리)

### 1) API/도메인 확장 (최우선)
- `BuildRequest`에 `fvm_flavor` 추가 (optional)
- 파이프라인 전 구간에 `fvm_flavor` 전파 및 상태 API에 노출

### 2) 버전 매핑 도입
- 루트에 `fvm_flavors.json` 추가
- 구조: `{ "<fvm_flavor>": { "flutter_version": "3.29.3", "cocoapods_version": "1.14.3" } }`
- 누락 시 기존 동작 유지(환경변수 `FLUTTER_VERSION` 사용, CocoaPods 고정 미적용)

### 3) 워킹 디렉토리 분리 전략
- `<BASE_LOCAL_DIR>-<fvm_flavor>`로 분리 (예: `/src/prod/app` → `/src/prod/app-winc1`)
- 파이프라인 시작 시 환경변수 `DEV_LOCAL_DIR`/`PROD_LOCAL_DIR`를 재정의하여 스크립트 변경 최소화

### 4) iOS CocoaPods 고정 실행
- iOS 스크립트(`action/*/1_ios.sh`)에서 `COCOAPODS_VERSION` 존재 시:
  - `gem install -N cocoapods -v $COCOAPODS_VERSION` (미설치 시)
  - `pod _$COCOAPODS_VERSION_ install --repo-update`
- 이후 `fvm exec fastlane <lane>` 기존 플로우 유지

### 5) 확장 포인트 (선택)
- fastlane/bundler 버전 고정 필요 시 유사 전략 적용 가능
- `DerivedData` 경로 분리(환경변수 `GYM_XCARCHIVE_PATH` 등)도 확장 가능

### 6) 테스트 계획
- 샘플 요청(JSON)으로 수동 빌드 트리거 → 상태 폴링으로 성공 확인
- 검증 항목
  - `builds`/`build/{id}`에 `fvm_flavor`가 반영되는지
  - 실 워킹 디렉토리가 `<BASE>-<fvm_flavor>`로 세팅되는지
  - `pod install`이 지정 버전으로 수행되는지 로그 확인


