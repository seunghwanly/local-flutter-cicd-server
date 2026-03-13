# 처음 Pull 받은 뒤 해야 할 일

이 프로젝트는 macOS 로컬에서 Flutter CI/CD 서버를 띄우는 용도입니다. 처음 clone 또는 pull 받은 뒤에는 아래 순서대로 진행하면 됩니다.

## 1. 필수 도구 확인

다음 명령이 먼저 있어야 합니다.

- `python3`
- `git`
- `fvm`
- `ruby`
- `bundle`
- `pod`
- 선택: `ngrok`

확인이 필요하면:

```bash
which python3 git fvm ruby bundle pod
```

## 2. 한 번에 설치와 점검

루트에서 아래 한 줄을 실행합니다.

```bash
bash install.sh
```

이 스크립트는 다음을 처리합니다.

- `venv` 생성
- Python 의존성 설치
- `.env`가 없으면 `env.template` 기반으로 생성
- 정적 점검 (`make doctor`)
- 단위 테스트 (`make test`)

## 3. `.env` 값 채우기

최소한 아래 값은 확인해야 합니다.

- `REPO_URL`
- `DEV_BRANCH_NAME`, `DEV_FASTLANE_LANE`
- `PROD_BRANCH_NAME`, `PROD_FASTLANE_LANE`
- iOS 빌드 시 `MATCH_PASSWORD`
- webhook 사용 시 `GITHUB_WEBHOOK_SECRET`

## 4. 서버 실행

```bash
make run
```

서버가 뜨면 아래 주소를 확인합니다.

- Swagger: `http://127.0.0.1:8000/docs`
- Dashboard: `http://127.0.0.1:8000/dashboard`
- Diagnostics: `http://127.0.0.1:8000/diagnostics`

## 5. 첫 검증

먼저 diagnostics가 정상인지 확인합니다.

```bash
curl http://127.0.0.1:8000/diagnostics
```

그 다음 수동 빌드 API 또는 webhook으로 실제 빌드를 한 번 태워봅니다.

## 6. Flutter SDK 관련 주의

이 서버는 저장소의 `.fvmrc` 또는 `.tool-versions`를 우선 따라갑니다.  
새로 pull 받은 코드의 Flutter SDK 버전이 이전과 다르면, 빌드 전에 자동으로 `fvm flutter precache --ios`가 먼저 실행됩니다.
