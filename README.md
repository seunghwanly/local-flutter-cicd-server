# 🚀 Flutter CI/CD Container

GitHub Webhook을 수신하고 Flutter 프로젝트를 자동 빌드하는 개발 환경입니다.

## 📦 지원 기능

- FastAPI 기반 Webhook 수신 서버
- Flutter SDK 자동 설치 (버전 지정 가능)
- Ruby + Fastlane 설치 포함
- Android / iOS 빌드 환경 지원
- 단일 `.env` 환경변수 파일 관리 방식

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
| ✅ Flutter 버전 | `FLUTTER_VERSION` | `3.29.3` | 사용할 Flutter SDK 버전 |
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

- 실행 시 `/src`, `/src/dev`, `/src/prod` 디렉토리가 자동으로 생성됩니다.
- Python 가상환경이 생성되고 `uvicorn`을 통해 FastAPI 서버가 실행됩니다.

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
├── Dockerfile
├── entrypoint.sh
├── main.py
├── requirements.txt
├── action/
│   ├── dev/0_setup.sh
│   ├── dev/1_android.sh
│   ├── dev/1_ios.sh
│   └── prod/... (동일 구조)
├── src/              # Git clone 대상 디렉토리
├── .dockerignore
├── .env
```

---

## 🙋 FAQ

**Q. .android.env, .ios.env은 사용되나요?**  
A. 아니요. 현재는 `.env` 하나로 모든 설정을 통합하고 있습니다.

**Q. ngrok은 포함되나요?**  
A. 아닙니다. 각자 환경에 맞게 구성해야 합니다.

**Q. FVM은 지원하나요?**  
A. 아니요. Flutter는 직접 설치되며 `flutter` 명령어를 그대로 사용합니다.

---

## 🔐 Webhook 보안

Webhook 시그니처 검증을 위해 `GITHUB_WEBHOOK_SECRET` 환경변수를 설정할 수 있습니다 (optional).

```bash
-e GITHUB_WEBHOOK_SECRET=your-secret
```

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
