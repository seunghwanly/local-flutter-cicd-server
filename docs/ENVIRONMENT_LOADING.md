# 환경변수 로딩 메커니즘

## 📋 개요

이 프로젝트는 `.env` 파일을 사용하여 환경변수를 관리합니다. 
**중요:** `.env` 파일은 셸 스크립트가 `source` 하지 않습니다. FastAPI 앱 시작 시 `pydantic-settings`가 프로젝트 루트의 `.env`를 읽고, 필요한 값을 `os.environ`으로 미러링합니다.

---

## 🔄 환경변수 로딩 방법

### 방법 1: scripts/start.sh 사용 (권장) ✅

`scripts/start.sh --foreground`는 가상환경 준비와 의존성 설치를 처리한 뒤 `uvicorn`을 실행합니다. `.env` 파일 자체는 앱 시작 과정에서 Python 설정 계층이 읽습니다.

```bash
./scripts/start.sh --foreground
```

**사용법:**
```bash
./scripts/start.sh --foreground
```

**장점:**
- ✅ 간단하고 편리
- ✅ 가상환경 자동 설정
- ✅ requirements.txt 자동 설치
- ✅ 디렉토리 자동 생성

---

### 방법 2: 직접 실행

직접 실행해도 루트 `.env`는 자동으로 읽힙니다.

```bash
# 1. 가상환경 활성화
source venv/bin/activate

# 2. 서버 실행
./venv/bin/uvicorn src.main:app --reload
```

**주의사항:**
- ⚠️ 앱이 자동으로 읽는 대상은 프로젝트 루트의 `.env`입니다.
- ⚠️ 셸에서 `export $(cat .env | xargs)` 방식으로 수동 로드하면 멀티라인 값이 깨질 수 있습니다.

---

## 🤔 왜 별도 셸 로딩을 쓰지 않나요?

### 이유

1. **중복 방지**: `scripts/start.sh`가 가상환경 준비와 실행을 함께 처리합니다.
2. **일관성**: `scripts/start.sh`와 직접 `uvicorn` 실행 모두 같은 `AppSettings` 경로를 사용합니다.
3. **안전성**: 멀티라인 값도 `.env` 파서가 그대로 읽을 수 있습니다.

### 코드 비교

**현재:**
```python
model_config = SettingsConfigDict(
    env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "src" / ".env"),
    env_file_encoding="utf-8",
    extra="ignore",
)
```

---

## 🐳 Docker 환경

Docker를 사용하는 경우, Dockerfile에서 환경변수를 설정하거나 `docker-compose.yml`에서 `env_file`을 지정하세요.

### docker-compose.yml 예시

```yaml
services:
  app:
    build: .
    env_file:
      - .env
    ports:
      - "8000:8000"
```

---

## 🧪 환경변수 확인

서버 시작 시 환경변수가 제대로 로드되었는지 확인:

```bash
curl http://localhost:8000/diagnostics
```

---

## 📚 관련 문서

- [ENV_SETUP_GUIDE.md](./ENV_SETUP_GUIDE.md) - 환경변수 설정 가이드
- [env.template](./env.template) - 환경변수 템플릿
- [scripts/start.sh](../scripts/start.sh) - 서버 시작 스크립트

---

## ⚠️ 트러블슈팅

### 문제 1: 환경변수가 로드되지 않음

**증상:**
```
RuntimeError: 환경변수 GITHUB_WEBHOOK_SECRET이 설정되지 않았습니다.
```

**해결:**
```bash
# .env 파일이 존재하는지 확인
ls -la .env

# .env 파일 내용 확인
cat .env | grep GITHUB_WEBHOOK_SECRET

# 앱 시작 후 진단 확인
./scripts/start.sh --foreground
curl http://localhost:8000/diagnostics
```

### 문제 2: 멀티라인 값 (Private Key) 문제

**증상:**
```
bash: syntax error near unexpected token `('
```

**해결:**

`.env` 파일에서 멀티라인 값을 따옴표로 감싸세요:

```bash
# 올바른 형식
APPSTORE_API_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----
MIGTAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBHkwdwIBAQQg...
-----END PRIVATE KEY-----"
```

그리고 서버는 `./scripts/start.sh --foreground` 또는 `./venv/bin/uvicorn src.main:app ...`로 실행하세요. `.env`는 앱이 직접 읽습니다.

---

**업데이트:** 2026-03-17  
**버전:** 2.1 (AppSettings 기반 `.env` 로딩 반영)
