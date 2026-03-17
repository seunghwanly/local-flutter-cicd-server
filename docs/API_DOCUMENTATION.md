# Flutter CI/CD Server API 명세서

## 개요

Flutter CI/CD Server는 Flutter 애플리케이션의 빌드 파이프라인을 관리하는 REST API 서버입니다. GitHub webhook을 통한 자동 빌드 트리거와 수동 빌드 트리거를 지원합니다.

## 서버 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 서버 실행
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## API 문서 접근

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## API 엔드포인트

### 1. 서버 상태 확인

**GET** `/`

서버가 정상적으로 실행 중인지 확인합니다.

**응답 예시:**
```json
{
  "message": "👋 Flutter CI/CD Container is running!"
}
```

### 2. 빌드 목록 조회

**GET** `/builds`

모든 빌드의 현재 상태를 조회합니다.

**응답 예시:**
```json
{
  "builds": [
    {
      "build_id": "dev-all-20241201-143022",
      "status": "completed",
      "started_at": "2024-12-01T14:30:22",
      "flavor": "dev",
      "platform": "all",
      "branch_name": "develop",
      "build_name": null,
      "build_number": null
    }
  ]
}
```

### 3. 빌드 상태 조회

**GET** `/build/{build_id}`

특정 빌드 ID의 상세 상태와 로그를 조회합니다.

**경로 파라미터:**
- `build_id` (string): 조회할 빌드의 고유 ID

**응답 예시:**
```json
{
  "build_id": "dev-all-20241201-143022",
  "status": "running",
  "started_at": "2024-12-01T14:30:22",
  "flavor": "dev",
  "platform": "all",
  "branch_name": "develop",
  "build_name": null,
  "build_number": null,
  "processes": {
    "setup": {
      "running": false,
      "return_code": 0
    },
    "android": {
      "running": true,
      "return_code": null
    },
    "ios": {
      "running": true,
      "return_code": null
    }
  },
  "progress": {
    "android": {
      "current_step": "building",
      "percentage": 75,
      "steps_completed": [
        {
          "step": "setup",
          "status": "SUCCESS",
          "message": "Setup completed",
          "timestamp": "2024-12-01T14:30:25"
        }
      ],
      "current_message": "Building APK..."
    }
  },
  "logs": [
    "[SETUP] Setting up environment...",
    "[ANDROID] Starting Android build...",
    "[ANDROID] 📊 Building APK... (75%)"
  ]
}
```

### 4. 수동 빌드 트리거

**POST** `/build`

빌드를 수동으로 트리거합니다.

**요청 본문:**
```json
{
  "flavor": "dev",
  "platform": "all",
  "build_name": "custom-build",
  "build_number": "1.2.3",
  "branch_name": "develop",
  "fvm_flavor": "winc1"
}
```

**요청 파라미터:**
- `flavor` (string, 선택사항): 빌드 환경 ("dev" 또는 "prod"). 기본값: "dev"
- `platform` (string, 선택사항): 대상 플랫폼 ("all", "android", "ios"). 기본값: "all"
- `build_name` (string, 선택사항): 커스텀 빌드 이름
- `build_number` (string, 선택사항): 커스텀 빌드 번호
- `branch_name` (string, 선택사항): 빌드할 Git 브랜치 이름
- `fvm_flavor` (string, 선택사항): FVM/Pods 버전 키. 루트의 `fvm_flavors.json`에서 버전 매핑을 조회합니다

**응답 예시:**
```json
{
  "status": "manual trigger ok",
  "build_id": "dev-all-20241201-143022"
}
```

### 5. GitHub Actions

**POST** `/github-action/build`

GitHub에서 전송되는 일반 build action 이벤트를 처리합니다.

**헤더:**
- `X-Hub-Signature-256`: GitHub webhook 서명
- `X-Hub-Signature`: GitHub webhook 서명 (sha1 fallback)
- `X-GitHub-Event`: GitHub 이벤트 타입

**지원하는 이벤트:**
- **PR 머지**: release/dev* 브랜치로 머지될 때 dev 빌드 트리거
- **태그 생성**: x.y.z 형식의 태그가 생성될 때 prod 빌드 트리거

### 6. 수동 Shorebird 빌드

**POST** `/build/shorebird`

Shorebird patch 배포용 빌드를 수동으로 트리거합니다.

**요청 파라미터:**
- `flavor` (string, 선택사항): `dev`, `stg`, `stage`, `prd`, `prod` 지원. 비우면 `SHOREBIRD_PATCH_FLAVOR` 또는 `prod`
- `platform` (string, 선택사항): 대상 플랫폼 ("all", "android", "ios")
- `build_name` (string, 선택사항): Shorebird release/tag name
- `build_number` (string, 선택사항): Shorebird patch number
- `branch_name` (string, 선택사항): 빌드할 Git 브랜치 이름

**응답 예시:**
```json
{
  "status": "ok",
  "build_id": "dev-all-20241201-143022"
}
```

## 빌드 상태

- `pending`: 빌드 대기 중
- `running`: 빌드 실행 중
- `completed`: 빌드 완료
- `failed`: 빌드 실패

## 플랫폼 옵션

- `all`: Android와 iOS 모두 빌드
- `android`: Android만 빌드
- `ios`: iOS만 빌드

## 환경 옵션

- `dev`: 개발 환경 빌드
- `prod`: 프로덕션 환경 빌드

## curl 예시

### 서버 상태 확인
```bash
curl -X GET "http://localhost:8000/"
```

### 빌드 목록 조회
```bash
curl -X GET "http://localhost:8000/builds"
```

### 특정 빌드 상태 조회
```bash
curl -X GET "http://localhost:8000/build/dev-all-20241201-143022"
```

### 수동 빌드 트리거
```bash
curl -X POST "http://localhost:8000/build" \
  -H "Content-Type: application/json" \
  -d '{
    "flavor": "dev",
    "platform": "all",
    "branch_name": "develop"
  }'
```

### 커스텀 빌드
```bash
curl -X POST "http://localhost:8000/build" \
  -H "Content-Type: application/json" \
  -d '{
    "flavor": "prod",
    "platform": "android",
    "build_name": "release-v2.1.0",
    "build_number": "2.1.0",
    "branch_name": "main"
  }'
```

## 환경 변수

- `GITHUB_WEBHOOK_SECRET`: GitHub webhook 서명 검증을 위한 시크릿 키

## 에러 코드

- `404`: 빌드를 찾을 수 없음
- `403`: GitHub webhook 서명이 유효하지 않음
- `422`: 요청 데이터가 유효하지 않음

## 모니터링

빌드 진행 상황을 실시간으로 모니터링하려면:

```bash
# 빌드 상태 주기적 확인
while true; do
  curl -s "http://localhost:8000/build/$BUILD_ID" | jq '.status, .progress'
  sleep 5
done
``` 
