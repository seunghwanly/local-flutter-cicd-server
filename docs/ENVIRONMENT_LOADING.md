# 환경변수 로딩 메커니즘

## 📋 개요

이 프로젝트는 `.env` 파일을 사용하여 환경변수를 관리합니다. 
**중요:** `main.py`에서 `python-dotenv`를 사용하지 않고, `local_run.sh`에서 환경변수를 로드합니다.

---

## 🔄 환경변수 로딩 방법

### 방법 1: local_run.sh 사용 (권장) ✅

`local_run.sh` 스크립트가 자동으로 `.env` 파일을 로드합니다.

```bash
#!/bin/bash
# local_run.sh에서 자동 처리
set -a
[ -f .env ] && . .env
set +a
```

**사용법:**
```bash
sh local_run.sh
```

**장점:**
- ✅ 간단하고 편리
- ✅ 가상환경 자동 설정
- ✅ requirements.txt 자동 설치
- ✅ 디렉토리 자동 생성

---

### 방법 2: 직접 실행

`.env` 파일을 수동으로 로드한 후 서버를 실행합니다.

```bash
# 1. 환경변수 로드
export $(cat .env | xargs)

# 2. 서버 실행
uvicorn main:app --reload
```

**주의사항:**
- ⚠️ `.env` 파일에 줄바꿈이 포함된 값(예: PRIVATE_KEY)이 있으면 문제가 될 수 있습니다.
- 이 경우 `set -a; source .env; set +a` 사용을 권장합니다.

---

## 🤔 왜 python-dotenv를 사용하지 않나요?

### 이유

1. **중복 방지**: `local_run.sh`에서 이미 환경변수를 로드하고 있습니다.
2. **의존성 최소화**: 불필요한 Python 패키지를 추가하지 않습니다.
3. **일관성**: 모든 환경변수 로딩을 한 곳(local_run.sh)에서 관리합니다.

### 코드 비교

**이전 (python-dotenv 사용):**
```python
from dotenv import load_dotenv
load_dotenv()  # 중복!
```

**현재 (간소화):**
```python
# Note: .env 파일은 local_run.sh에서 자동으로 로드됩니다
# 직접 실행 시: export $(cat .env | xargs) && uvicorn main:app --reload
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
# 환경변수 출력 (주의: 민감한 정보 포함)
echo $WORKSPACE_ROOT
echo $GITHUB_WEBHOOK_SECRET

# 또는 Python에서 확인
python -c "import os; print(os.environ.get('WORKSPACE_ROOT'))"
```

---

## 📚 관련 문서

- [ENV_SETUP_GUIDE.md](./ENV_SETUP_GUIDE.md) - 환경변수 설정 가이드
- [env.template](./env.template) - 환경변수 템플릿
- [local_run.sh](./local_run.sh) - 서버 시작 스크립트

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

# local_run.sh 사용
sh local_run.sh
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

그리고 `local_run.sh`를 사용하세요 (더 안전한 파싱).

---

**업데이트:** 2025-10-02  
**버전:** 2.0 (python-dotenv 제거)

