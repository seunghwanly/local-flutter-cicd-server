# 🚀 Flutter CI/CD Server

수동 빌드 요청과 GitHub action 이벤트를 수신해 Flutter 프로젝트를 자동 빌드하는 FastAPI 기반 CI/CD 서버입니다.

## 📦 지원 기능

- **FastAPI 기반 GitHub Action 수신 서버** - 일반 빌드와 Shorebird patch 이벤트 처리
- **Flutter SDK 자동 설치** - 버전별 격리된 환경 지원
- **Python 오케스트레이션 우선** - Git sync, 브랜치 정렬, Flutter 버전 해석을 Python이 담당
- **Android / iOS 빌드 환경** - Ruby + Fastlane 포함
- **완전 격리된 빌드 환경** - PUB_CACHE, GRADLE_USER_HOME, GEM_HOME, CP_HOME_DIR 격리
- **버전별 캐싱 전략** - Flutter, Gradle, CocoaPods 버전별 공유 캐시로 빌드 시간 단축
- **큐 기반 동시성 제어** - 동일 브랜치는 순차, 다른 브랜치는 병렬 실행
- **자동 캐시 정리** - 7일 이상 된 빌드 자동 삭제

## 🚀 실행 가이드

처음 pull 받은 뒤 바로 따라갈 수 있는 절차는 [`docs/FIRST_PULL_GUIDE.md`](./docs/FIRST_PULL_GUIDE.md)에 정리했습니다.

### 0. 필수 사전 요구사항

iOS 빌드를 위해서는 rbenv와 Ruby가 필요합니다:

```bash
# rbenv 설치 (Homebrew 사용)
brew install rbenv ruby-build

# rbenv 초기화 (셸 설정 파일에 추가)
echo 'eval "$(rbenv init - zsh)"' >> ~/.zshrc  # zsh 사용 시
# 또는
echo 'eval "$(rbenv init - bash)"' >> ~/.bash_profile  # bash 사용 시

# 셸 재시작 또는 설정 파일 다시 로드
source ~/.zshrc  # 또는 source ~/.bash_profile

# Ruby 설치 (권장 버전: 3.2.0 이상)
rbenv install 3.2.0
rbenv shell 3.2.0

# 설치 확인
ruby -v
```

**참고:** `.env` 파일에서 `RUBY_VERSION` 환경변수를 설정하여 특정 Ruby 버전을 사용할 수 있습니다:
```bash
RUBY_VERSION=3.2.0
```

### 1. 환경 설정

```bash
# 환경변수 파일 생성
cp env.template .env
```

`.env` 파일을 열어서 실제 값으로 수정하세요:

| 항목 | 키 | 설명 |
|------|----|------|
| Flutter 버전 | `FLUTTER_VERSION` | `.fvmrc`/`.tool-versions`가 없을 때만 쓰는 fallback Flutter SDK 버전 |
| Git 리포 | `REPO_URL` | Git 리포지토리 주소 |
| 브랜치 이름 | `DEV_BRANCH_NAME` / `PROD_BRANCH_NAME` | 배포 대상 브랜치 |
| Fastlane Lane | `DEV_FASTLANE_LANE` / `PROD_FASTLANE_LANE` | Fastlane에서 실행할 lane 이름 |
| Webhook 서명 | `GITHUB_WEBHOOK_SECRET` | GitHub Webhook 보안 키 |
| Slack | `SLACK_WEBHOOK_CHANNEL` | Slack Webhook URL |

### 2. 서버 실행

```bash
# 1회 부트스트랩
make bootstrap

# 로컬 실행
make run
```

설정 진단:

```bash
curl http://localhost:8000/diagnostics
```

`/diagnostics`는 webhook env뿐 아니라 `git`, `fvm`, `ruby`, `bundle`, `pod` 경로와 주요 version fallback env 상태도 함께 보여줍니다.

또는 직접 실행:

```bash
./venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### 3. 외부 접속 설정 (ngrok)

```bash
# ngrok 설치 및 실행
brew install ngrok
make tunnel
```

GitHub Build Action 설정:
- Payload URL: `https://xxxx.ngrok-free.app/github-action/build`
- Content type: `application/json`
- Secret: `.env`의 `GITHUB_WEBHOOK_SECRET`
- 이벤트: `Pull requests`, `Create (tags)`
- 기본 정책:
  - `release-dev-v* -> develop` 머지 시 `dev`
  - `develop -> main` 머지 시 `prod`
  - `x.y.z` 태그 생성 시 `prod`

GitHub Shorebird Action 설정:
- Payload URL: `https://xxxx.ngrok-free.app/github-action/shorebird`
- Secret: `.env`의 `GITHUB_WEBHOOK_SECRET`
- 기본 빌드 대상은 `.env`의 `SHOREBIRD_PATCH_FLAVOR`, `SHOREBIRD_PATCH_PLATFORM`, `SHOREBIRD_PATCH_BRANCH_NAME`

주의:
- `GITHUB_WEBHOOK_SECRET`이 없으면 해당 `POST /github-action/*` 엔드포인트는 `503`을 반환합니다.
- 기존 `/webhook`은 호환용 alias로 유지됩니다.
- 수동 빌드 API와 상태 조회는 GitHub secret 없이도 로컬에서 사용할 수 있습니다.
- 빌드에 필요한 env가 빠져 있으면 `/build`는 누락 키 목록과 함께 즉시 실패합니다.
- 저장소를 새로 pull한 뒤 Flutter SDK 버전이 바뀌면, 빌드 전에 Python 오케스트레이터가 `fvm flutter precache --ios`를 반드시 먼저 실행합니다.
- Python setup이 `pub get`, cache repair, Bundler/gem 준비를 담당하고, shell 스크립트는 실제 플랫폼 빌드 실행 위주로 남겨둡니다.

## 📁 프로젝트 구조

```
src/
├── main.py               # 🎯 애플리케이션 진입점
├── api/                  # View 계층 (FastAPI 라우트)
│   └── routes.py         # API 엔드포인트 정의
├── models/               # 데이터 모델 (Pydantic)
│   └── models.py         # API 요청/응답 스키마
├── core/                 # 핵심 비즈니스 로직
│   ├── config.py         # 설정 관리 및 격리된 환경 생성
│   └── queue_manager.py  # 빌드 큐 관리
├── services/             # 비즈니스 로직 서비스
│   ├── build_service.py  # 빌드 파이프라인 서비스
│   ├── action_service.py # GitHub build / shorebird action 서비스
│   └── webhook_service.py # GitHub action 호환 alias
└── utils/                # 유틸리티 함수들
    └── cleanup.py        # 캐시 정리 스케줄러
```

### 🔄 의존성 방향

```
api/ → models/, services/, core/, utils/
services/ → core/, utils/
core/ → utils/
```

## 🔑 인증 설정 도우미

이 서버는 두 가지 Git 인증 방식을 지원합니다:
- **SSH 인증**: `GITHUB_TOKEN`이 없을 때 사용 (SSH 키 필요)
- **HTTPS 인증**: `GITHUB_TOKEN`이 있을 때 자동으로 사용 (SSH 체크 건너뜀)

### GitHub Token 추가 방법 (PAT)

`GITHUB_TOKEN`을 설정하면 SSH 인증을 건너뛰고 HTTPS 인증을 사용합니다.

1. **GitHub Personal Access Token 생성:**
   - GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
   - "Generate new token" 클릭
   - Scopes: `repo` (Full control of private repositories) 체크
   - 생성된 토큰 복사 (예: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)

2. **.env 파일에 토큰 추가:**
   ```bash
   # REPO_URL은 SSH 또는 HTTPS 형식 모두 가능
   REPO_URL=git@github.com:your_org/your_repo.git
   # 또는
   REPO_URL=https://github.com/your_org/your_repo.git
   
   # GitHub Token 추가 (HTTPS 인증 사용)
   GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

**참고:** `GITHUB_TOKEN`이 설정되어 있으면 SSH 키 체크를 건너뛰고 HTTPS 인증을 사용합니다.

### git-credential 사용 방법

```bash
# 방법 A: Git credential helper 사용
git config --global credential.helper store
cd ~/your-private-repo
git pull  # 토큰 입력 (username은 아무거나, password는 token)

# 방법 B: 직접 파일 생성
echo "https://<your-token>@github.com" > ~/.git-credentials
chmod 600 ~/.git-credentials
```

### pubspec.yaml에 Git 의존성이 있는 경우

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
```
