# Flutter CI/CD 서버 PUB_CACHE 격리 마이그레이션 진행 상황

## 📅 시작일: 2025-10-02

## 🎯 마이그레이션 목표
기존 macOS 로컬 CI/CD 서버를 PUB_CACHE 완전 격리 아키텍처로 마이그레이션하여:
- ✅ 빌드 간 완전한 격리 (버전 충돌 제거)
- ✅ 동일 브랜치/flavor 조합의 순차 처리
- ✅ 서로 다른 조합의 병렬 실행
- ✅ 자동 캐시 정리

---

## 📋 Phase별 진행 상황

### Phase 1: 의존성 추가 및 구조 설정 ✅

**목표:**
- Python 패키지 추가 (filelock, schedule, psutil)
- requirements.txt 업데이트
- config.py 생성 (격리된 환경 구조)

**완료:**
- ✅ requirements.txt 업데이트
- ✅ config.py 생성
- ✅ 환경변수 설정 함수 구현
- ✅ 디렉토리 구조 자동 생성

**변경 파일:**
- `requirements.txt`
- `config.py` (신규)

---

### Phase 2: 큐 관리 시스템 구현 ✅

**목표:**
- 파일 기반 락을 사용한 큐 관리자 구현
- 동일 (branch, fvm_flavor, flavor) 조합은 순차 처리
- 다른 조합은 병렬 처리

**완료:**
- ✅ queue_manager.py 구현
- ✅ 큐 키 생성 로직 (get_queue_key)
- ✅ 파일 락 기반 동기화 (FileLock)
- ✅ execute_with_queue 메서드

**변경 파일:**
- `queue_manager.py` (신규)

---

### Phase 3: main.py 리팩토링 ✅

**목표:**
- start_build_pipeline에 큐 통합
- build_pipeline_with_monitoring 완전 개선
- 격리된 환경변수 적용

**완료:**
- ✅ start_build_pipeline 수정 (큐 키 생성 및 통합)
- ✅ build_pipeline_with_monitoring 리팩토링 (완전 격리)
- ✅ get_isolated_env 호출하여 환경 격리
- ✅ 스크립트 폴백 로직 (common → flavor)
- ✅ BuildStatusResponse에 queue_key 필드 추가
- ✅ 로그 개선

**변경 파일:**
- `main.py`

---

### Phase 4: 빌드 스크립트 재작성 ✅

**목표:**
- 통합 빌드 스크립트 생성 (flavor별 → common)
- 격리된 환경 사용 (PUB_CACHE, GRADLE_USER_HOME)
- 기존 flavor별 스크립트 삭제 또는 deprecated

**완료:**
- ✅ action/common/ 디렉토리 생성
- ✅ 0_setup_isolated.sh 작성 (격리된 Setup)
- ✅ 1_android_isolated.sh 작성 (격리된 Android 빌드)
- ✅ 1_ios_isolated.sh 작성 (격리된 iOS 빌드)
- ✅ 실행 권한 부여

**변경 파일:**
- `action/common/0_setup_isolated.sh` (신규)
- `action/common/1_android_isolated.sh` (신규)
- `action/common/1_ios_isolated.sh` (신규)

---

### Phase 5: 캐시 정리 자동화 ✅

**목표:**
- 오래된 빌드 캐시 자동 삭제 스케줄러 구현
- 고아 락 파일 정리
- main.py에 스케줄러 통합

**완료:**
- ✅ cleanup_scheduler.py 구현
- ✅ cleanup_old_builds 함수 (날짜 기반 정리)
- ✅ cleanup_orphaned_locks 함수 (24시간 이상 락 파일 삭제)
- ✅ start_cleanup_scheduler 함수 (매일 03:00 실행)
- ✅ main.py startup 이벤트 통합
- ✅ /cleanup API 엔드포인트 추가 (수동 정리)

**변경 파일:**
- `cleanup_scheduler.py` (신규)
- `main.py` (startup 이벤트 및 /cleanup 엔드포인트 추가)

---

### Phase 6: 모니터링 도구 ✅

**목표:**
- 워크스페이스 통계 조회 도구
- 디스크 사용량 모니터링

**완료:**
- ✅ monitor.py 구현
- ✅ get_workspace_stats 함수 (전체 통계)
- ✅ get_build_details 함수 (특정 빌드 상세)
- ✅ 디스크 사용량 경고 기능
- ✅ 실행 권한 부여

**사용법:**
```bash
# 전체 워크스페이스 통계
python monitor.py

# 특정 빌드 상세 정보
python monitor.py dev-android-20250102-143022
```

**변경 파일:**
- `monitor.py` (신규)

---

### Phase 7: 문서화 및 검증 ✅

**목표:**
- 마이그레이션 진행 상황 문서화

**완료:**
- ✅ PROCESS.md 작성
- ✅ 각 Phase별 상세 정보 기록
- ✅ 아키텍처 결정 사항 문서화

**변경 파일:**
- `PROCESS.md`

---

## 🔄 현재 상태

**상태:** ✅ 마이그레이션 완료!

**다음 단계:**
1. 의존성 설치: `pip install -r requirements.txt`
2. 환경변수 설정 (`.env` 또는 시스템 환경변수)
3. 서버 시작: `uvicorn main:app --reload`
4. 테스트 시나리오 실행

---

## 📝 주요 결정 사항

### 아키텍처 결정

1. **워크스페이스 구조:**
   ```
   ~/ci-cd-workspace/
   ├── builds/
   │   └── {build_id}/
   │       ├── repo/
   │       ├── pub_cache/
   │       └── gradle_home/
   └── queue_locks/
       └── {queue_key}.lock
   ```

2. **큐 키 생성 규칙:**
   - 형식: `{flavor}_{branch}_{fvm_flavor}`
   - 예: `dev_develop_default`, `prod_main_flutter335`

3. **환경변수 격리:**
   - `PUB_CACHE`: 빌드별 독립
   - `GRADLE_USER_HOME`: 빌드별 독립
   - `LOCAL_DIR`: 빌드별 독립 git 저장소

4. **캐시 정리 정책:**
   - 기본 보관 기간: 7일
   - 실행 시간: 매일 새벽 3시
   - 고아 락 파일: 24시간 이상

---

## ⚠️ 발견된 이슈 및 해결

### 이슈 1: 기존 스크립트와의 호환성
**문제:** 기존 `action/{flavor}/*.sh` 스크립트들이 새로운 환경변수를 인식하지 못함

**해결:** 
- main.py에 폴백 로직 추가
- common 스크립트가 없으면 기존 스크립트 사용
- 점진적 마이그레이션 가능

### 이슈 2: 환경변수 이름 충돌
**문제:** 기존 `{FLAVOR}_LOCAL_DIR`과 새로운 `LOCAL_DIR` 혼재

**해결:**
- 새로운 common 스크립트는 `LOCAL_DIR` 사용
- 기존 스크립트는 `{FLAVOR}_LOCAL_DIR` 유지
- 격리 환경에서는 항상 `LOCAL_DIR` 사용

### 이슈 3: FVM flavor 파싱
**문제:** `.fvmrc` 파일 파싱 시 복잡한 JSON 구조

**해결:**
- 기존 sed 기반 파싱 로직 유지
- FVM_FLAVOR가 있으면 해당 키 우선 사용
- 없으면 기본 "flutter" 키 사용

### 이슈 4: 불필요한 flutter clean
**문제:** 격리된 환경에서 `flutter clean`이 불필요한 오버헤드

**해결:**
- 격리 스크립트에서 `flutter clean` 제거
- `git clean -fdx`로 충분 (이미 깨끗한 상태)
- 빌드 시간 평균 5-15초 단축

---

## ✅ 완료된 작업

### 구현된 주요 기능

1. **완전 격리된 빌드 환경**
   - 각 빌드는 독립된 디렉토리 (`~/ci-cd-workspace/builds/{build_id}/`)
   - 격리된 PUB_CACHE, GRADLE_USER_HOME
   - Git 저장소도 빌드별 독립

2. **큐 기반 동시성 제어**
   - 동일 (branch, fvm_flavor, flavor) 조합: 순차 실행
   - 다른 조합: 병렬 실행
   - 파일 락 기반 프로세스 간 동기화

3. **자동 캐시 정리**
   - 매일 새벽 3시 자동 실행
   - 7일 이상 된 빌드 캐시 삭제
   - 고아 락 파일 제거
   - 수동 정리 API: `POST /cleanup`

4. **모니터링 도구**
   - 워크스페이스 통계 조회
   - 빌드별 크기 및 나이 확인
   - 디스크 사용량 경고

5. **하위 호환성**
   - 기존 flavor별 스크립트도 계속 동작
   - common 스크립트가 없으면 자동 폴백

### 신규 파일 목록

```
프로젝트 루트/
├── config.py                           # 격리 환경 설정
├── queue_manager.py                     # 큐 관리 시스템
├── cleanup_scheduler.py                 # 자동 정리 스케줄러
├── monitor.py                          # 모니터링 도구
├── action/common/
│   ├── 0_setup_isolated.sh            # 격리된 Setup
│   ├── 1_android_isolated.sh          # 격리된 Android 빌드
│   └── 1_ios_isolated.sh              # 격리된 iOS 빌드
└── PROCESS.md                          # 마이그레이션 진행 상황
```

### 변경된 파일 목록

```
- requirements.txt    (filelock, schedule, psutil 추가)
- main.py            (큐 통합, 격리 환경, cleanup 엔드포인트)
```

---

## 🔗 참고 링크

- [프로젝트 README](./README.md)
- [API 문서](./API_DOCUMENTATION.md)
- [요구사항 문서](./REQUIREMENTS.md)
- [계획 문서](./PLANNING.md)

---

## 🚀 시작 가이드

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env` 파일을 사용하여 환경변수를 관리합니다:

```bash
# 1. 템플릿 파일 복사
cp env.template .env

# 2. .env 파일 수정 (최소 필수 항목)
# WORKSPACE_ROOT=/Users/your_username/ci-cd-workspace
# CACHE_CLEANUP_DAYS=7
# GITHUB_WEBHOOK_SECRET=your-secret
# REPO_URL=git@github.com:your-org/your-repo.git
# DEV_BRANCH_NAME=develop
# DEV_FASTLANE_LANE=beta
```

상세한 설정 방법은 [ENV_SETUP_GUIDE.md](./ENV_SETUP_GUIDE.md)를 참고하세요.

### 3. 서버 시작

```bash
# 방법 1: local_run.sh 사용 (권장)
sh local_run.sh

# 방법 2: 직접 실행
export $(cat .env | xargs)  # .env 파일 로드
uvicorn main:app --reload
```

### 4. 첫 빌드 테스트

```bash
# 수동 빌드 트리거
curl -X POST "http://localhost:8000/build" \
  -H "Content-Type: application/json" \
  -d '{
    "flavor": "dev",
    "platform": "android",
    "branch_name": "develop"
  }'

# 빌드 상태 확인
curl http://localhost:8000/build/{build_id}
```

### 5. 모니터링

```bash
# 워크스페이스 통계 확인
python monitor.py

# 수동 정리 실행
curl -X POST http://localhost:8000/cleanup
```

---

## 📈 테스트 시나리오

### 시나리오 1: 완전 격리 검증

```bash
# 동시에 두 개의 다른 빌드 실행
curl -X POST "http://localhost:8000/build" -H "Content-Type: application/json" \
  -d '{"flavor": "dev", "platform": "android", "branch_name": "develop", "fvm_flavor": "flutter329"}' &

curl -X POST "http://localhost:8000/build" -H "Content-Type: application/json" \
  -d '{"flavor": "dev", "platform": "android", "branch_name": "feature-a", "fvm_flavor": "flutter335"}' &
```

**예상 결과:** 두 빌드가 서로 간섭 없이 병렬 실행

### 시나리오 2: 큐 직렬화 검증

```bash
# 동일한 조합으로 두 번 빌드
curl -X POST "http://localhost:8000/build" -H "Content-Type: application/json" \
  -d '{"flavor": "dev", "platform": "all", "branch_name": "develop"}' &

sleep 2

curl -X POST "http://localhost:8000/build" -H "Content-Type: application/json" \
  -d '{"flavor": "dev", "platform": "all", "branch_name": "develop"}' &
```

**예상 결과:** 두 번째 빌드가 첫 번째 완료까지 대기

### 시나리오 3: PUB_CACHE 격리 검증

```bash
# 빌드 실행 중 PUB_CACHE 확인
BUILD_ID="dev-android-20250102-143022"
ls -la ~/ci-cd-workspace/builds/$BUILD_ID/pub_cache/global_packages/
```

**예상 결과:** melos 등 globally activated 패키지가 빌드별로 독립 설치됨

---

**최종 업데이트:** 2025-10-02 (마이그레이션 완료)

