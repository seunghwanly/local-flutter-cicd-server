# 🔑 Git 인증 설정 가이드

Flutter CI/CD 서버에서 private Git repository에 접근하기 위한 설정 가이드입니다.

## 📋 목차

1. [개요](#개요)
2. [SSH 인증 (권장)](#ssh-인증-권장)
3. [HTTPS 인증 (Personal Access Token)](#https-인증-personal-access-token)
4. [pubspec.yaml Git 의존성 처리](#pubspecyaml-git-의존성-처리)
5. [문제 해결](#문제-해결)

---

## 개요

이 서버는 다음 두 가지 Git 인증 방식을 지원합니다:

| 방식 | 장점 | 단점 | 사용 케이스 |
|------|------|------|-------------|
| **SSH** | 안전, 설정 간단 | SSH 키 관리 필요 | 기본 repository clone |
| **HTTPS** | Token으로 관리 용이 | Token 노출 위험 | pubspec.yaml의 Git 의존성 |

### 동작 원리

1. **메인 Repository Clone**: `REPO_URL` 환경변수로 지정 (SSH/HTTPS 모두 가능)
2. **pubspec.yaml Git 의존성**: HTTPS로 선언된 경우 `GITHUB_TOKEN` 또는 `.git-credentials` 사용

---

## SSH 인증 (권장)

### 1단계: SSH 키 생성

```bash
# ED25519 키 생성 (권장)
ssh-keygen -t ed25519 -C "your_email@example.com"

# 또는 RSA 키 생성
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
```

**파일 위치:**
- Private key: `~/.ssh/id_ed25519` (또는 `id_rsa`)
- Public key: `~/.ssh/id_ed25519.pub` (또는 `id_rsa.pub`)

### 2단계: GitHub에 Public Key 등록

```bash
# Public key 출력
cat ~/.ssh/id_ed25519.pub
```

GitHub 설정:
1. GitHub → Settings → SSH and GPG keys
2. "New SSH key" 클릭
3. Title: "CI/CD Server" (또는 원하는 이름)
4. Key: 복사한 public key 붙여넣기
5. "Add SSH key" 클릭

### 3단계: SSH Agent 설정 (선택사항)

```bash
# SSH Agent 시작
eval "$(ssh-agent -s)"

# 키 추가
ssh-add ~/.ssh/id_ed25519

# 자동 시작 설정 (macOS)
cat >> ~/.ssh/config << EOF
Host *
  AddKeysToAgent yes
  UseKeychain yes
  IdentityFile ~/.ssh/id_ed25519
EOF
```

### 4단계: .env 파일 설정

```bash
# SSH URL 사용
REPO_URL=git@github.com:your_org/your_repo.git
```

### 동작 확인

```bash
# GitHub 연결 테스트
ssh -T git@github.com

# 출력 예시:
# Hi username! You've successfully authenticated, but GitHub does not provide shell access.
```

---

## HTTPS 인증 (Personal Access Token)

pubspec.yaml에 `https://github.com/...` 형식의 Git 의존성이 있는 경우 필수입니다.

### 1단계: GitHub Personal Access Token 생성

1. GitHub → Settings → Developer settings
2. Personal access tokens → Tokens (classic)
3. "Generate new token (classic)" 클릭
4. Note: "CI/CD Server" (또는 원하는 이름)
5. Expiration: 원하는 기간 선택 (권장: 1년)
6. Scopes 선택:
   - ✅ `repo` (Full control of private repositories) **필수**
7. "Generate token" 클릭
8. 생성된 토큰 복사 (예: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)
   - ⚠️ 주의: 이 토큰은 다시 볼 수 없으므로 안전한 곳에 저장하세요

### 2단계: .env 파일에 토큰 추가

```bash
# .env 파일
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# HTTPS URL 사용 (선택사항)
REPO_URL=https://github.com/your_org/your_repo.git
```

### 3단계 (대안): 시스템에 .git-credentials 파일 생성

Token을 .env에 넣고 싶지 않은 경우:

```bash
# 방법 A: Git credential helper 사용
git config --global credential.helper store

# Private repo에서 한번 pull 실행
cd ~/your-private-repo
git pull
# Username: your-github-username
# Password: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx (토큰 입력)

# 이제 ~/.git-credentials 파일이 생성됨
cat ~/.git-credentials
# https://your-username:ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx@github.com
```

```bash
# 방법 B: 직접 파일 생성
echo "https://ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx@github.com" > ~/.git-credentials
chmod 600 ~/.git-credentials

# Git config 설정
git config --global credential.helper store
```

### 동작 확인

```bash
# Token이 올바른지 확인
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user

# 출력 예시:
# {
#   "login": "your-username",
#   "id": 12345,
#   ...
# }
```

---

## pubspec.yaml Git 의존성 처리

### 시나리오 1: HTTPS Git 의존성

```yaml
dependencies:
  my_package:
    git:
      url: https://github.com/your_org/my_package.git
      ref: main
```

**필요한 설정:**
- `.env` 파일에 `GITHUB_TOKEN` 추가
- 또는 `~/.git-credentials` 파일 생성

**동작:**
1. `config.py`의 `setup_git_credentials()` 함수가 자동으로 실행
2. `GITHUB_TOKEN`이 있으면 빌드 디렉토리에 `.git-credentials` 파일 생성
3. 없으면 시스템의 `~/.git-credentials` 복사
4. Git이 자동으로 credential을 사용하여 private repo 접근

### 시나리오 2: SSH Git 의존성 (변환 필요)

```yaml
dependencies:
  my_package:
    git:
      url: git@github.com:your_org/my_package.git
      ref: main
```

**필요한 설정:**
- SSH 키 설정 (위의 SSH 인증 섹션 참고)

---

## 문제 해결

### 문제 1: `pub get` 실패 - Git 의존성 접근 불가

```
Git error. Command: `git clone --mirror https://github.com/org/package.git`
stderr: 
fatal: could not read Username for 'https://github.com': terminal prompts disabled
```

**해결 방법:**
1. `GITHUB_TOKEN` 환경변수 설정 확인:
   ```bash
   echo $GITHUB_TOKEN
   ```

2. `.git-credentials` 파일 확인:
   ```bash
   cat ~/.git-credentials
   ```

3. Token 유효성 확인:
   ```bash
   curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
   ```

### 문제 2: 특정 ref (브랜치/태그)를 찾을 수 없음

```
Git error: The ref 'feature-branch' could not be found in 'https://github.com/org/package.git'
```

**해결 방법:**
1. Remote repository에 브랜치가 존재하는지 확인:
   ```bash
   git ls-remote --heads https://github.com/org/package.git | grep feature-branch
   ```

2. 브랜치가 없으면 pubspec.yaml 수정:
   ```yaml
   dependencies:
     my_package:
       git:
         url: https://github.com/your_org/my_package.git
         ref: main  # 존재하는 브랜치로 변경
   ```

### 문제 3: Git 캐시 손상

```
Git error: fatal: not a git repository
```

**해결 방법:**
1. 수동으로 캐시 정리:
   ```bash
   rm -rf ~/.pub-cache/git/cache/*
   ```

2. 또는 Flutter pub cache repair:
   ```bash
   flutter pub cache repair
   ```

3. Setup 스크립트가 자동으로 손상된 캐시 감지 및 정리:
   - `action/common/0_setup_isolated.sh`의 "🧹 Checking for corrupted git caches" 로그 확인

### 문제 4: SSH 인증 실패

```
git@github.com: Permission denied (publickey)
```

**해결 방법:**
1. SSH Agent 실행 확인:
   ```bash
   eval "$(ssh-agent -s)"
   ssh-add ~/.ssh/id_ed25519
   ```

2. SSH 연결 테스트:
   ```bash
   ssh -T git@github.com
   ```

3. GitHub에 public key가 등록되었는지 확인

### 문제 5: 빌드 로그에서 자세한 정보 확인

Setup 스크립트는 verbose 모드로 실행되며 다음 정보를 제공합니다:

```bash
🔐 Checking Git credentials configuration...
✅ Git credential helper configured: store --file=/path/to/.git-credentials
✅ Git HTTPS credentials available

📋 Git dependencies found in pubspec.yaml:
  git:
    url: https://github.com/org/package.git
    ref: main

🔍 Testing Git repository access...
  Testing: https://github.com/org/package.git
    ✅ Access OK
```

로그를 확인하여 어떤 단계에서 문제가 발생했는지 파악할 수 있습니다.

---

## 보안 권장사항

### 1. Token 권한 최소화

- 필요한 최소 권한만 부여 (`repo` scope)
- 만료 기간 설정

### 2. Token 저장 위치

- ✅ 환경변수 (.env 파일)
- ✅ .git-credentials 파일 (권한: 600)
- ❌ 코드에 하드코딩
- ❌ 공개 repository에 포함

### 3. .git-credentials 파일 권한 확인

```bash
# 파일 권한 확인
ls -la ~/.git-credentials

# 출력 예시:
# -rw-------  1 user  staff  89 Jan 10 10:00 .git-credentials

# 권한이 잘못된 경우 수정
chmod 600 ~/.git-credentials
```

### 4. Token 로테이션

- 주기적으로 Token 재발급 (예: 3-6개월)
- 이전 Token 삭제

---

## 테스트 체크리스트

### SSH 인증
- [ ] SSH 키 생성 완료
- [ ] GitHub에 public key 등록 완료
- [ ] `ssh -T git@github.com` 성공
- [ ] `.env`에 SSH URL 설정 (`git@github.com:...`)
- [ ] 빌드 실행 시 repository clone 성공

### HTTPS 인증
- [ ] GitHub Personal Access Token 생성 완료
- [ ] `.env`에 `GITHUB_TOKEN` 추가 또는 `.git-credentials` 파일 생성
- [ ] `curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user` 성공
- [ ] pubspec.yaml의 Git 의존성 접근 성공
- [ ] 빌드 로그에서 "✅ Git HTTPS credentials available" 확인

---

## 요약

**간단 설정 (5분):**

1. **SSH만 사용하는 경우:**
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   cat ~/.ssh/id_ed25519.pub  # GitHub에 등록
   ```
   `.env`: `REPO_URL=git@github.com:your_org/your_repo.git`

2. **HTTPS도 사용하는 경우 (pubspec.yaml에 Git 의존성):**
   ```bash
   # GitHub에서 Personal Access Token 생성 (repo 권한)
   ```
   `.env`: `GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

3. **서버 재시작:**
   ```bash
   ./scripts/start.sh --foreground
   ```

완료! 🎉
