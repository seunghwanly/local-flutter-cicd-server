## 문제 정의 및 요구사항 (FVM/Pods 버전 분리)

### 배경
- 프로젝트가 FVM을 통해 브랜치/제품 라인별로 서로 다른 Flutter SDK 버전을 사용하고 있음
- 동일한 iOS `Pods` 디렉토리, 동일한 CocoaPods 버전을 공유할 경우 종종 버전 충돌이 발생하여 빌드가 실패함
- Android도 Gradle/Wrappers가 버전별 영향을 받으나, 별도 워킹 디렉토리 분리로 충돌을 회피 가능

### 현재 문제
- API의 `BuildRequest`가 Flutter 버전 선택을 직접적으로 표현하지 못함 → 런타임에 어떤 Flutter 버전을 사용할지 안정적으로 결정하기 어려움
- iOS 빌드 시 CocoaPods 버전이 고정되지 않아 버전 업/다운에 따른 충돌 발생
- 동일한 로컬 clone 디렉토리(예: `DEV_LOCAL_DIR`, `PROD_LOCAL_DIR`)를 다수 버전이 공유하여 `ios/Pods`, `Podfile.lock`, `DerivedData` 등이 뒤섞여 충돌

### 목표
- API 레벨에서 `fvm_flavor`를 받아 Flutter SDK 버전 및 iOS CocoaPods 버전을 안정적으로 선택
- `fvm_flavor`별로 완전히 분리된 워킹 디렉토리(로컬 clone path)를 사용해 iOS `Pods`와 Android Gradle 아티팩트를 격리
- iOS CocoaPods 버전을 `fvm_flavor`별로 고정하여 설치/실행 (예: `pod _1.14.3_ install`)
- 변경은 현재 파이프라인(설정 스크립트, iOS/Android 빌드 스크립트)에 최소 침습적으로 적용

### 범위
- FastAPI `BuildRequest`에 `fvm_flavor` 필드 추가 및 파이프라인 전파
- `fvm_flavors.json` 매핑 파일 도입: `fvm_flavor` → `{ flutter_version, cocoapods_version }`
- 빌드 파이프라인에서 환경변수 설정:
  - `FLUTTER_VERSION`를 매핑으로 결정
  - `COCOAPODS_VERSION`를 매핑으로 결정
  - `DEV_LOCAL_DIR`/`PROD_LOCAL_DIR`를 `-<fvm_flavor>` 접미사로 분리된 경로로 재정의 (예: `/src/proj` → `/src/proj-winc1`)
- iOS 스크립트에서 CocoaPods 버전 고정 실행(`pod _X.Y.Z_ install --repo-update`)

### 비범위(Out of Scope)
- 기존 리포의 `Podfile`/`Gemfile` 수정 강제는 하지 않음 (선택적)
- Ruby 버전/fastlane 버전 별도 고정은 옵션으로 남김 (필요 시 확장)

### 성공 기준 (Acceptance Criteria)
1. 다음 요청으로 iOS(prod) 빌드가 성공
```json
{
  "flavor": "prod",
  "platform": "ios",
  "build_name": "1.23.10",
  "build_number": "555",
  "branch_name": "main",
  "fvm_flavor": "winc1"
}
```
2. 해당 빌드는 `PROD_LOCAL_DIR-winc1` 같은 분리된 경로에서 수행되어, 다른 `fvm_flavor` 빌드와 충돌하지 않음
3. CocoaPods가 매핑된 버전으로 설치/실행되어 `pod install`이 일관되게 동작


