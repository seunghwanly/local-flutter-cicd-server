# 🚀 Flutter CI/CD Container

GitHub Webhook을 수신하고 Flutter 프로젝트를 자동 빌드하는 개발 환경입니다.

## 📦 지원 기능

- FastAPI 기반 Webhook 수신 서버
- Flutter SDK 자동 설치 (버전 지정 가능)
- Ruby + Fastlane 설치 포함
- Android / iOS 빌드 환경 지원
- 단일 `.env` 환경변수 파일 관리 방식
- **🆕 완전 격리된 빌드 환경** (PUB_CACHE, GRADLE_USER_HOME, GEM_HOME, CP_HOME_DIR)
- **🆕 버전별 캐싱 전략** (Flutter, Gradle, CocoaPods 버전별 공유 캐시로 빌드 시간 98% 단축)
- **🆕 큐 기반 동시성 제어** (동일 브랜치는 순차, 다른 브랜치는 병렬)
- **🆕 자동 캐시 정리** (7일 이상 된 빌드 자동 삭제)

---

## ✅ 실행 순서 가이드

이 프로젝트를 clone 받고 실행하는 전체 흐름은 다음과 같습니다:

### 1. `.env.template` 복사 → `.env` 파일 생성

```bash
cp .env.template .env
```

`.env` 파일 내 값을 알맞게 수정합니다.

#### 🛠️ `.env` 파일 항목

| 항목 | 키 | 예시 값 | 설명 |
|------|----|---------|------|
| ✅ Flutter 버전 | `FLUTTER_VERSION` | `3.29.3` | 사용할 Flutter SDK 버전 (또는 `fvm_flavor`로 대체 가능) |
| ✅ Git 리포 | `REPO_URL` | `git@github.com:your_org/your_repo.git` | Git 리포지토리 주소 |
| ✅ 브랜치 이름 | `DEV_BRANCH_NAME` / `PROD_BRANCH_NAME` | `develop` / `main` | 배포 대상 브랜치 |
| ✅ Clone 디렉토리 | `DEV_LOCAL_DIR` / `PROD_LOCAL_DIR` | `./src/dev/your_proj` | 로컬 clone 경로 |
| ✅ Fastlane Lane | `DEV_FASTLANE_LANE` / `PROD_FASTLANE_LANE` | `deploy_dev` | Fastlane에서 실행할 lane 이름 |
| ✅ Webhook 서명 | `GITHUB_WEBHOOK_SECRET` | `your_signature` | GitHub Webhook 보안 키 |
| ✅ Slack | `SLACK_WEBHOOK_CHANNEL` | `https://hooks.slack.com/...` | Slack Webhook URL |
| ✅ App Store Keychain | `KEYCHAIN_NAME`, `KEYCHAIN_PASSWORD` | `login.keychain` | 키체인 이름/비밀번호 |
| ✅ App Store API | `APPSTORE_API_KEY_ID`, `APPSTORE_ISSUER_ID` | `ABC123XYZ`, `issuer-uuid` | Apple API 인증 정보 |
| ✅ App Store 키 | `APPSTORE_API_PRIVATE_KEY` | `"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"` | PEM 키 전체 문자열 (줄바꿈 포함) |
| ✅ Play Store 키 | `GOOGLE_SERVICE_ACCOUNT_JSON` | base64 문자열 | Google 서비스 계정 키(base64 인코딩) |

`.env.template` 파일을 참고해 실제 값으로 수정해 사용하세요.


### 2. FastAPI 서버 실행

로컬 테스트용으로 다음 명령어를 실행하세요:

```bash
sh local_run.sh
```

- Python 가상환경이 생성되고 `uvicorn`을 통해 FastAPI 서버가 실행됩니다.
- 새로운 구조에서는 `src/main.py`가 애플리케이션 진입점입니다.

### 3. 외부 도메인에서 로컬 서버로 Webhook 포워딩 (ngrok 사용)

FastAPI는 `localhost:8000`에서 실행되므로 외부 접속이 불가능합니다. 외부 Webhook을 수신하려면 포워딩이 필요합니다.

```bash
brew install ngrok
ngrok http 8000
```

ngrok 실행 시 출력되는 주소 (`https://xxxx.ngrok-free.app`)를 GitHub Webhook 설정에 사용합니다:

- Payload URL: `https://xxxx.ngrok-free.app/webhook`
- Content type: `application/json`
- Secret: `.env`의 `GITHUB_WEBHOOK_SECRET`
- 이벤트: `Pull requests`, `Create (tags)`


---

## 📁 주요 구조

```
.
├── requirements.txt           # Python 의존성
├── local_run.sh              # 로컬 실행 스크립트
├── env.template              # 환경변수 템플릿
├── fvm_flavors.json          # FVM 버전 매핑
├── src/                      # 소스 코드
│   ├── __init__.py
│   ├── main.py               # 🎯 애플리케이션 진입점
│   ├── api/                  # View 계층 (FastAPI 라우트)
│   │   ├── __init__.py
│   │   └── routes.py         # API 엔드포인트
│   ├── models/               # 데이터 모델 (Pydantic)
│   │   ├── __init__.py
│   │   └── models.py         # API 요청/응답 모델
│   ├── core/                 # 핵심 비즈니스 로직
│   │   ├── __init__.py
│   │   ├── config.py         # 설정 관리
│   │   └── queue_manager.py  # 빌드 큐 관리
│   ├── services/             # 비즈니스 로직 서비스
│   │   ├── __init__.py
│   │   ├── build_service.py  # 빌드 파이프라인 서비스
│   │   └── webhook_service.py # GitHub Webhook 서비스
│   └── utils/                # 유틸리티 함수들
│       ├── __init__.py
│       ├── cleanup.py         # 캐시 정리 스케줄러
│       └── monitoring.py      # 모니터링 도구
├── action/                   # 빌드 스크립트
│   ├── 0_setup.sh            # 환경 설정
│   ├── 1_android.sh          # Android 빌드
│   └── 1_ios.sh              # iOS 빌드
├── docs/                     # 프로젝트 문서
│   ├── API_DOCUMENTATION.md
│   ├── CACHE_STRATEGY.md
│   ├── ENV_SETUP_GUIDE.md
│   ├── GIT_AUTHENTICATION.md
│   └── ... (기타 문서)
└── .env                      # 환경변수 (생성 필요)
```

---

## 🏗️ 프로젝트 구조 설명

### 📦 패키지별 역할

- **`src/api/`** - View 계층 (FastAPI 라우트)
  - REST API 엔드포인트 정의
  - HTTP 요청/응답 처리

- **`src/models/`** - 데이터 모델 (Pydantic)
  - API 요청/응답 스키마 정의
  - 데이터 검증 및 직렬화

- **`src/core/`** - 핵심 비즈니스 로직
  - 설정 관리 (`config.py`)
  - 빌드 큐 관리 (`queue_manager.py`)

- **`src/services/`** - 비즈니스 로직 서비스
  - 빌드 파이프라인 서비스 (`build_service.py`)
  - GitHub Webhook 서비스 (`webhook_service.py`)

- **`src/utils/`** - 유틸리티 함수들
  - 캐시 정리 스케줄러 (`cleanup.py`)
  - 모니터링 도구 (`monitoring.py`)

### 🔄 의존성 방향

```
api/ → models/, services/, core/, utils/
services/ → core/, utils/
core/ → utils/
```

### 🎯 실행 방식

- **로컬 실행**: `sh local_run.sh` → `python3 -m src.main`
- **모듈 실행**: `python3 -m src.main` (패키지 방식)
- **직접 실행**: `python3 src/main.py` (파일 방식)

---

## 🙋 FAQ

**Q. .android.env, .ios.env은 사용되나요?**  
A. 아니요. 현재는 `.env` 하나로 모든 설정을 통합하고 있습니다.

**Q. ngrok은 포함되나요?**  
A. 아닙니다. 각자 환경에 맞게 구성해야 합니다.

**Q. FVM은 지원하나요?**  
A. FVM을 사용합니다. `fvm_flavor`로 Flutter 버전과 CocoaPods 버전을 선택할 수 있으며, 루트의 `fvm_flavors.json`에 매핑합니다.

**Q. 새로운 프로젝트 구조의 장점은?**  
A. 관심사 분리, 확장성, 유지보수성이 향상되었습니다. 각 패키지가 명확한 역할을 가지며, 의존성 방향이 단방향으로 설계되었습니다.

**Q. main.py가 src/ 안에 있는 이유는?**  
A. 모든 소스 코드를 `src/` 패키지로 통합하여 더 깔끔한 구조를 만들었습니다. `python3 -m src.main` 방식으로 모듈 실행이 가능합니다.

---

## 🔐 Webhook 보안

Webhook 시그니처 검증을 위해 `GITHUB_WEBHOOK_SECRET` 환경변수를 설정할 수 있습니다 (optional).

```bash
-e GITHUB_WEBHOOK_SECRET=your-secret
```

---

## 🔑 Git 인증 설정 (Private Repository)

Private repository에 접근하려면 Git 인증 설정이 필요합니다. SSH와 HTTPS 두 가지 방법을 지원합니다.

### 방법 1: SSH 인증 (권장)

1. **SSH 키 생성 및 등록:**
```bash
# SSH 키 생성 (이미 있으면 생략)
ssh-keygen -t ed25519 -C "your_email@example.com"

# Public key를 GitHub에 등록
cat ~/.ssh/id_ed25519.pub
# → GitHub → Settings → SSH and GPG keys → New SSH key
```

2. **.env 파일에서 SSH URL 사용:**
```bash
REPO_URL=git@github.com:your_org/your_repo.git
```

3. **SSH Agent 실행 (선택사항):**
```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

### 방법 2: HTTPS 인증 (Personal Access Token)

pubspec.yaml에 `http`로 선언된 private Git repository를 사용하는 경우 필수입니다.

1. **GitHub Personal Access Token 생성:**
   - GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
   - "Generate new token" 클릭
   - Scopes: `repo` (Full control of private repositories) 체크
   - 생성된 토큰 복사 (예: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)

2. **.env 파일에 토큰 추가:**
```bash
# HTTPS URL 사용
REPO_URL=https://github.com/your_org/your_repo.git

# GitHub Token 추가
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

3. **또는 로컬에 .git-credentials 파일 생성:**
```bash
# 방법 A: Git credential helper 사용
git config --global credential.helper store
cd ~/your-private-repo
git pull  # 토큰 입력 (username은 아무거나, password는 token)

# 방법 B: 직접 파일 생성
echo "https://<your-token>@github.com" > ~/.git-credentials
chmod 600 ~/.git-credentials
```

### pubspec.yaml의 Git 의존성 인증

pubspec.yaml에 Git 의존성이 있는 경우:

```yaml
dependencies:
  my_package:
    git:
      url: https://github.com/your_org/my_package.git
      ref: feature-branch
```

위와 같은 경우 `GITHUB_TOKEN` 환경변수나 `.git-credentials` 파일이 자동으로 사용됩니다.

**문제 해결:**
```bash
# 1. Token이 올바른지 확인
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user

# 2. .git-credentials 확인
cat ~/.git-credentials

# 3. Git 캐시 초기화 (문제 발생 시)
rm -rf ~/.pub-cache/git/cache/*

# 4. 빌드 로그에서 Git 접근 테스트 결과 확인
# Setup 스크립트가 자동으로 Git repository 접근을 테스트합니다
```

**자세한 설정은 [GIT_AUTHENTICATION.md](./docs/GIT_AUTHENTICATION.md)를 참고하세요.**

---

## # 선택사항: Mac mini + Docker 조합으로 사용하기

Mac mini 환경에서 Docker를 사용할 경우:

- Docker 컨테이너 안에서는 FastAPI 서버만 실행
- 빌드 스크립트는 Mac 호스트에서 직접 실행 (예: `ssh localhost` 또는 로컬 쉘)

예시:

```bash
ssh your_mac_user@localhost "bash /absolute/path/to/action/dev/0_setup.sh"
```

iOS 빌드는 반드시 macOS에서만 가능하므로 이 구조를 추천합니다.

---

## 🔄 마이그레이션 (PUB_CACHE 격리)

### 주요 변경사항

2025-10-02에 PUB_CACHE 완전 격리 아키텍처로 마이그레이션되었습니다.

**개선점:**
- ✅ 빌드 간 완전한 격리 (버전 충돌 제거)
- ✅ 동일 브랜치/flavor 조합의 순차 처리
- ✅ 서로 다른 조합의 병렬 실행
- ✅ 자동 캐시 정리 (매일 새벽 3시)

**새로운 환경변수:**

`.env` 파일에 추가하세요:
```bash
WORKSPACE_ROOT=/Users/your_username/ci-cd-workspace
CACHE_CLEANUP_DAYS=7
```

자세한 설정은 [ENV_SETUP_GUIDE.md](./docs/ENV_SETUP_GUIDE.md)를 참고하세요.

**상세 문서:**
- [PROCESS.md](./docs/PROCESS.md) - 마이그레이션 진행 상황 및 아키텍처
- [REQUIREMENTS.md](./docs/REQUIREMENTS.md) - 요구사항 문서

**마이그레이션 검증:**
```bash
# 1. .env 파일 생성 (env.template 참고)
cp env.template .env
# .env 파일을 열어서 실제 값으로 수정

# 2. local_run.sh로 시작 (권장)
sh local_run.sh

# 또는 직접 실행
pip install -r requirements.txt
export $(cat .env | xargs)
python3 -m src.main
```

**모니터링:**
```bash
# 워크스페이스 통계 확인
python3 -m src.utils.monitoring

# 수동 캐시 정리
curl -X POST http://localhost:8000/cleanup
```

---

## 📚 추가 자료

### 프로젝트 문서
- [Git 인증 설정 가이드](./docs/GIT_AUTHENTICATION.md) - SSH/HTTPS 인증 상세 가이드
- [환경변수 설정 가이드](./docs/ENV_SETUP_GUIDE.md) - .env 파일 설정
- [마이그레이션 가이드](./docs/PROCESS.md) - PUB_CACHE 격리 아키텍처
- [API 문서](./docs/API_DOCUMENTATION.md) - REST API 명세

### 외부 문서
- FastAPI 공식 문서: https://fastapi.tiangolo.com/
- Flutter 공식 문서: https://flutter.dev/
- Fastlane 공식 문서: https://docs.fastlane.tools/
