# 🚀 Flutter CI/CD Container

GitHub Webhook을 수신하고 Flutter 프로젝트를 자동 빌드하는 Docker 개발 환경입니다.

## 📦 지원 기능

- FastAPI 기반 Webhook 수신 서버
- Flutter SDK 자동 설치 (버전 지정 가능)
- Ruby + Fastlane 설치 포함
- Android / iOS 빌드 환경 지원
- `.android.env`, `.ios.env` 환경변수 mount 지원

---

## 🛠️ 사용 방법

### 1. `.env`, `.android.env`, `.ios.env` 파일 준비

루트 경로에 다음 파일들을 생성하세요:

#### 1-1. `.env` 파일 생성

```bash
cp .env.template .env
```

`.env` 파일을 열어 아래 항목을 자신의 환경에 맞게 설정합니다.

| 변수명                  | 설명                                      | 필수 여부 |
|------------------------|-----------------------------------------|----------|
| `FLUTTER_VERSION`       | 설치할 Flutter SDK 버전 예: `3.22.2`         | ✅        |
| `REPO_URL`              | Git 리포지토리 주소                        | ✅        |
| `DEV_BRANCH_NAME`       | 개발 브랜치 이름 예: `develop`              | ✅        |
| `PROD_BRANCH_NAME`      | 운영 브랜치 이름 예: `main`                 | ✅        |
| `DEV_LOCAL_DIR`         | 개발 환경 clone 경로 예: `src/dev/your_proj` | ✅        |
| `PROD_LOCAL_DIR`        | 운영 환경 clone 경로 예: `src/prod/your_proj`| ✅        |
| `DEV_FASTLANE_LANE`     | 개발용 Fastlane lane 이름 예: `deploy_dev`   | ✅        |
| `PROD_FASTLANE_LANE`    | 운영용 Fastlane lane 이름 예: `deploy_prod`  | ✅        |
| `GITHUB_WEBHOOK_SECRET` | GitHub Webhook 시그니처 검증 키              | ⭕ (권장) |

#### 1-2. `.android.env` 파일 생성

```bash
cp .android.env.template .android.env
```

`.android.env` 파일을 열어 FASTLANE_USER, FASTLANE_PASSWORD, SLACK_WEBHOOK_CHANNEL 등을 자신의 환경에 맞게 설정합니다.

#### 1-3. `.ios.env` 파일 생성

```bash
cp .ios.env.template .ios.env
```

`.ios.env` 파일을 열어 FASTLANE_USER, KEYCHAIN 정보, APPSTORE_API_KEY_ID 등을 설정합니다.

---

## 🔨 이미지 빌드

```bash
docker build -t flutter-cicd \
  --build-arg FLUTTER_VERSION=3.22.2 \
  .
```

## ▶️ 컨테이너 실행

```bash
docker run \
  -v $(pwd)/.android.env:/workspace/.android.env \
  -v $(pwd)/.ios.env:/workspace/.ios.env \
  -p 8000:8000 \
  -e REPO_URL=git@github.com:your_org/your_repo.git \
  -e DEV_BRANCH_NAME=develop \
  -e PROD_BRANCH_NAME=main \
  -e DEV_LOCAL_DIR=src/dev/your_proj \
  -e PROD_LOCAL_DIR=src/prod/your_proj \
  -e DEV_FASTLANE_LANE=deploy_dev \
  -e PROD_FASTLANE_LANE=deploy_prod \
  -e GITHUB_WEBHOOK_SECRET=your_secret \
  flutter-local-cicd
```

---

## 📡 Webhook 등록 및 외부 테스트 준비 (ngrok 사용)

FastAPI 서버가 `localhost:8000` 에서 실행되고 있지만, GitHub Webhook은 외부 인터넷에서 접속해야 합니다.

따라서 ngrok으로 포트를 포워딩해야 합니다:

### 1. ngrok 설치

```bash
brew install ngrok
```

또는 [ngrok 공식 사이트](https://ngrok.com/)에서 설치

### 2. ngrok 실행

```bash
ngrok http 8000
```

실행하면 다음과 같은 화면이 나옵니다:

```
Forwarding                    https://xxxxxx.ngrok-free.app -> http://localhost:8000
```

이 `https://xxxxxx.ngrok-free.app` 주소를 GitHub Webhook에 등록하면 됩니다!

### 3. Webhook 등록

GitHub 리포지토리 > Settings > Webhooks 에서:

- Payload URL: `https://xxxxxx.ngrok-free.app/webhook`
- Content type: `application/json`
- Secret: `.env`에서 지정한 `GITHUB_WEBHOOK_SECRET`
- 이벤트: `Let me select individual events` → `Pull requests`, `Create` (tags)

> ⚠️ 참고: ngrok 무료 버전은 URL이 실행할 때마다 바뀔 수 있습니다. Webhook 설정도 매번 수정해야 합니다.

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
├── log/              # 로그 파일 저장소
├── .dockerignore
├── .env (mounted)
├── .android.env (mounted)
├── .ios.env (mounted)
```

---

## 🙋 FAQ

**Q. ngrok은 포함되나요?**  
A. 아닙니다. 포트 포워딩은 각자 환경에 맞게 구성해주세요.

**Q. FVM은 지원하나요?**  
A. 아니요. Flutter는 직접 설치되며 `flutter` 명령어를 그대로 사용합니다.

---

## 🧪 개발용 실행

```bash
uvicorn main:app --reload --port 8000
```

---

## 🔐 Webhook 보안

Webhook 시그니처 검증을 위해 `GITHUB_WEBHOOK_SECRET` 환경변수를 설정할 수 있습니다 (optional).

```bash
-e GITHUB_WEBHOOK_SECRET=your-secret
```

## 선택사항: Mac mini + Docker 조합으로 사용하기

만약 Mac mini 장비를 사용하고 있고, Docker 환경을 그대로 유지하고 싶다면 다음 방법으로 세팅할 수 있습니다:

### 1. Docker 컨테이너 안에서는 FastAPI 서버만 띄운다

- `uvicorn` 서버만 실행하고 빌드 스크립트(`action/dev/`, `action/prod/`)는 실행하지 않습니다.
- Webhook 수신 후 빌드 명령은 Mac 호스트(OS X)에서 직접 실행해야 합니다.

### 2. Mac 호스트의 리소스를 활용하여 빌드 스크립트를 실행한다

- Docker 컨테이너에서 webhook을 수신하면, `ssh localhost` 등을 통해 Mac 호스트에서 `bash action/dev/0_setup.sh` 같은 스크립트를 실행합니다.

```bash
ssh your_mac_user@localhost "bash /absolute/path/to/action/dev/0_setup.sh"
```

### 3. 주의사항

- iOS 빌드는 반드시 macOS 환경의 Xcode를 사용해야 하므로, Docker 리눅스 환경에서는 절대 빌드할 수 없습니다.
- Android 빌드는 Docker 컨테이너 안에서도 정상적으로 가능합니다.

### 4. 요약

| 항목 | 동작 환경 |
|:---|:---|
| FastAPI 서버 | Docker 컨테이너 (Mac mini 내부) |
| Android 빌드 | Docker 가능 |
| iOS 빌드 | 반드시 Mac 호스트 직접 실행 |

> 🚀 이 구조를 사용하면 Webhook 수신은 Docker로 격리하고, 실제 빌드는 Mac 자원을 직접 활용할 수 있습니다.
