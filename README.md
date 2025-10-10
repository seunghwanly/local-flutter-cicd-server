# 🚀 Flutter CI/CD Server

GitHub Webhook을 수신하고 Flutter 프로젝트를 자동 빌드하는 FastAPI 기반 CI/CD 서버입니다.

## 📦 지원 기능

- **FastAPI 기반 Webhook 수신 서버** - GitHub 이벤트 자동 처리
- **Flutter SDK 자동 설치** - 버전별 격리된 환경 지원
- **Android / iOS 빌드 환경** - Ruby + Fastlane 포함
- **완전 격리된 빌드 환경** - PUB_CACHE, GRADLE_USER_HOME, GEM_HOME, CP_HOME_DIR 격리
- **버전별 캐싱 전략** - Flutter, Gradle, CocoaPods 버전별 공유 캐시로 빌드 시간 단축
- **큐 기반 동시성 제어** - 동일 브랜치는 순차, 다른 브랜치는 병렬 실행
- **자동 캐시 정리** - 7일 이상 된 빌드 자동 삭제

## 🚀 실행 가이드

### 1. 환경 설정

```bash
# 환경변수 파일 생성
cp env.template .env
```

`.env` 파일을 열어서 실제 값으로 수정하세요:

| 항목 | 키 | 설명 |
|------|----|------|
| Flutter 버전 | `FLUTTER_VERSION` | 사용할 Flutter SDK 버전 |
| Git 리포 | `REPO_URL` | Git 리포지토리 주소 |
| 브랜치 이름 | `DEV_BRANCH_NAME` / `PROD_BRANCH_NAME` | 배포 대상 브랜치 |
| Fastlane Lane | `DEV_FASTLANE_LANE` / `PROD_FASTLANE_LANE` | Fastlane에서 실행할 lane 이름 |
| Webhook 서명 | `GITHUB_WEBHOOK_SECRET` | GitHub Webhook 보안 키 |
| Slack | `SLACK_WEBHOOK_CHANNEL` | Slack Webhook URL |

### 2. 서버 실행

```bash
# 로컬 실행
sh local_run.sh
```

또는 직접 실행:

```bash
pip install -r requirements.txt
python3 -m src.main
```

### 3. 외부 접속 설정 (ngrok)

```bash
# ngrok 설치 및 실행
brew install ngrok
ngrok http 8000
```

GitHub Webhook 설정:
- Payload URL: `https://xxxx.ngrok-free.app/webhook`
- Content type: `application/json`
- Secret: `.env`의 `GITHUB_WEBHOOK_SECRET`
- 이벤트: `Pull requests`, `Create (tags)`

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
│   └── webhook_service.py # GitHub Webhook 서비스
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

### GitHub Token 추가 방법 (PAT)

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