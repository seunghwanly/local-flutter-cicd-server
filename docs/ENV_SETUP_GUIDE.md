# 환경변수 설정 가이드

## 📦 .env 파일 생성

### 방법 1: 템플릿에서 복사 (권장)

```bash
cp env.template .env
```

그 다음 `.env` 파일을 열어서 실제 값으로 수정하세요.

**참고:** 
- `local_run.sh`를 사용하면 `.env` 파일이 자동으로 로드됩니다.
- 직접 서버를 실행할 경우: `export $(cat .env | xargs) && uvicorn main:app --reload`

### 방법 2: 직접 생성

`.env` 파일을 프로젝트 루트에 생성하고 아래 내용을 추가하세요.

---

## 🔑 필수 환경변수

### 마이그레이션 관련 (필수)

```bash
# 빌드 캐시가 저장될 워크스페이스 디렉토리
WORKSPACE_ROOT=/Users/your_username/ci-cd-workspace

# 빌드 캐시 보관 기간 (일)
CACHE_CLEANUP_DAYS=7
```

### Git & GitHub (필수)

```bash
# GitHub Webhook 시크릿
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here

# Git 리포지토리 URL
REPO_URL=git@github.com:your_org/your_repo.git
```

### Dev 환경 (필수)

```bash
# Dev 브랜치 이름
DEV_BRANCH_NAME=develop

# Dev Fastlane 레인
DEV_FASTLANE_LANE=beta
```

---

## ⚙️ 선택 환경변수

### 최대 병렬 빌드 수

```bash
# 기본값: 3
MAX_PARALLEL_BUILDS=3
```

### Flutter 버전

```bash
# FVM을 사용하지 않는 경우
FLUTTER_VERSION=3.29.3
```

### Prod/Stage 환경

```bash
# Prod 환경
PROD_BRANCH_NAME=main
PROD_FASTLANE_LANE=release

# Stage 환경
STAGE_BRANCH_NAME=staging
STAGE_FASTLANE_LANE=beta
```

### Slack 알림

```bash
SLACK_WEBHOOK_CHANNEL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### Apple App Store

```bash
KEYCHAIN_NAME=login.keychain
KEYCHAIN_PASSWORD=your_keychain_password
APPSTORE_API_KEY_ID=ABC123XYZ
APPSTORE_ISSUER_ID=your-issuer-uuid
APPSTORE_API_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----"
```

### Google Play Store

```bash
# base64로 인코딩된 서비스 계정 JSON
GOOGLE_SERVICE_ACCOUNT_JSON=ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsC...
```

---

## 📋 최소 설정 예시

빠르게 시작하려면 아래 최소 설정만으로도 충분합니다:

```bash
# .env 파일 내용

# 마이그레이션 관련
WORKSPACE_ROOT=/Users/myname/ci-cd-workspace
CACHE_CLEANUP_DAYS=7

# GitHub & Git
GITHUB_WEBHOOK_SECRET=my-secret-key
REPO_URL=git@github.com:myorg/myrepo.git

# Dev 환경
DEV_BRANCH_NAME=develop
DEV_FASTLANE_LANE=beta
```

---

## 🔍 환경변수 확인

서버 시작 시 로그에서 환경변수가 제대로 로드되었는지 확인할 수 있습니다:

```bash
uvicorn main:app --reload
```

출력 예시:
```
INFO:     📂 Workspace root: /Users/myname/ci-cd-workspace
INFO:     📂 Builds directory: /Users/myname/ci-cd-workspace/builds
INFO:     🔒 Queue locks directory: /Users/myname/ci-cd-workspace/queue_locks
INFO:     ✅ Cleanup scheduler started (keeping 7 days)
INFO:     ✅ Server ready at http://localhost:8000
```

---

## ⚠️ 주의사항

1. **절대 `.env` 파일을 Git에 커밋하지 마세요!**
   - `.gitignore`에 `.env`가 포함되어 있는지 확인하세요.

2. **경로는 절대 경로를 권장합니다:**
   ```bash
   # 좋은 예
   WORKSPACE_ROOT=/Users/myname/ci-cd-workspace
   
   # 나쁜 예 (상대 경로는 작업 디렉토리에 따라 달라질 수 있음)
   WORKSPACE_ROOT=./workspace
   ```

3. **멀티라인 값 (Private Key 등):**
   ```bash
   # 따옴표로 감싸야 합니다
   APPSTORE_API_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----
   MIGTAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBHkwdwIBAQQg...
   ...
   -----END PRIVATE KEY-----"
   ```

4. **Base64 인코딩:**
   ```bash
   # Google Service Account JSON을 base64로 인코딩
   cat service-account.json | base64
   ```

---

## 🧪 테스트

환경변수가 제대로 설정되었는지 테스트:

```bash
# 1. 마이그레이션 검증
python test_migration.py

# 2. 서버 시작
uvicorn main:app --reload

# 3. 테스트 빌드
curl -X POST "http://localhost:8000/build" \
  -H "Content-Type: application/json" \
  -d '{"flavor": "dev", "platform": "android", "branch_name": "develop"}'
```

---

## 📚 관련 문서

- [README.md](./README.md) - 프로젝트 전체 가이드
- [PROCESS.md](./PROCESS.md) - 마이그레이션 진행 상황
- [env.template](./env.template) - 환경변수 템플릿 파일

