# 🎉 Flutter CI/CD 서버 마이그레이션 완료 요약

## 📅 마이그레이션 일자
2025-10-02

## 🎯 마이그레이션 목표 달성

✅ **완전 격리**: 각 빌드는 독립된 PUB_CACHE, GRADLE_USER_HOME 사용  
✅ **큐 기반 동시성 제어**: 동일 조합은 순차, 다른 조합은 병렬  
✅ **자동 캐시 정리**: 7일 이상 된 빌드 자동 삭제  
✅ **하위 호환성**: 기존 스크립트도 계속 동작  

---

## 📊 구현된 기능

### 1. 완전 격리된 빌드 환경
각 빌드는 독립된 디렉토리 구조를 가집니다:

```
~/ci-cd-workspace/builds/{build_id}/
├── repo/          # Git 저장소
├── pub_cache/     # Dart/Flutter 패키지 캐시
└── gradle_home/   # Android Gradle 캐시
```

### 2. 큐 기반 동시성 제어
- **큐 키**: `{flavor}_{branch}_{fvm_flavor}`
- **동작**: 같은 큐 키는 순차 실행, 다른 큐 키는 병렬 실행
- **구현**: 파일 락(FileLock) 기반 프로세스 간 동기화

### 3. 자동 캐시 정리
- **스케줄**: 매일 새벽 3시 자동 실행
- **보관 기간**: 7일 (환경변수로 조정 가능)
- **고아 락 파일**: 24시간 이상 된 락 파일 자동 삭제
- **수동 정리**: `POST /cleanup` API 엔드포인트

### 4. 모니터링 도구
- 워크스페이스 통계 조회: `python monitor.py`
- 빌드별 상세 정보: `python monitor.py {build_id}`
- 디스크 사용량 경고 (80%, 90% 임계값)

---

## 📦 신규 파일

```
프로젝트 루트/
├── config.py                           # 격리 환경 설정
├── queue_manager.py                     # 큐 관리 시스템
├── cleanup_scheduler.py                 # 자동 정리 스케줄러
├── monitor.py                          # 모니터링 도구
├── test_migration.py                   # 마이그레이션 검증 스크립트
├── PROCESS.md                          # 마이그레이션 진행 상황
├── MIGRATION_SUMMARY.md                # 이 파일
└── action/common/
    ├── 0_setup_isolated.sh            # 격리된 Setup
    ├── 1_android_isolated.sh          # 격리된 Android 빌드
    └── 1_ios_isolated.sh              # 격리된 iOS 빌드
```

## 🔧 변경된 파일

```
- requirements.txt    # filelock, schedule, psutil 추가
- main.py            # 큐 통합, 격리 환경, startup 이벤트, /cleanup 엔드포인트
- README.md          # 마이그레이션 섹션 추가
```

---

## 🚀 시작하기

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env` 파일로 관리합니다:

```bash
# 1. 템플릿 복사
cp env.template .env

# 2. .env 파일 수정 (최소 필수 항목)
# WORKSPACE_ROOT=/Users/your_username/ci-cd-workspace
# REPO_URL=git@github.com:your-org/your-repo.git
# GITHUB_WEBHOOK_SECRET=your-secret
# DEV_BRANCH_NAME=develop
# DEV_FASTLANE_LANE=beta
# CACHE_CLEANUP_DAYS=7
```

자세한 설정은 [ENV_SETUP_GUIDE.md](./ENV_SETUP_GUIDE.md)를 참고하세요.

### 3. 마이그레이션 검증
```bash
python test_migration.py
```

### 4. 서버 시작
```bash
# 방법 1: local_run.sh 사용 (권장 - .env 자동 로드)
sh local_run.sh

# 방법 2: 직접 실행
pip install -r requirements.txt
export $(cat .env | xargs)  # .env 파일 로드
uvicorn main:app --reload
```

### 5. 첫 빌드 테스트
```bash
curl -X POST "http://localhost:8000/build" \
  -H "Content-Type: application/json" \
  -d '{
    "flavor": "dev",
    "platform": "android",
    "branch_name": "develop"
  }'
```

---

## 📈 API 변경사항

### 신규 엔드포인트

**POST /cleanup**
- 오래된 빌드 캐시 수동 정리
- 고아 락 파일 삭제

```bash
curl -X POST http://localhost:8000/cleanup
```

### 수정된 응답

**GET /build/{build_id}**
- `queue_key` 필드 추가 (빌드가 어느 큐에 속하는지 표시)

**GET /builds**
- 각 빌드에 `queue_key` 필드 추가

---

## 🧪 테스트 시나리오

### 시나리오 1: 완전 격리 검증
```bash
# 서로 다른 빌드 동시 실행
curl -X POST "http://localhost:8000/build" -H "Content-Type: application/json" \
  -d '{"flavor": "dev", "platform": "android", "branch_name": "develop", "fvm_flavor": "flutter329"}' &

curl -X POST "http://localhost:8000/build" -H "Content-Type: application/json" \
  -d '{"flavor": "dev", "platform": "android", "branch_name": "feature-a", "fvm_flavor": "flutter335"}' &
```

**예상 결과**: 두 빌드가 서로 간섭 없이 병렬 실행

### 시나리오 2: 큐 직렬화 검증
```bash
# 동일한 조합 두 번 빌드
curl -X POST "http://localhost:8000/build" -H "Content-Type: application/json" \
  -d '{"flavor": "dev", "platform": "all", "branch_name": "develop"}' &

sleep 2

curl -X POST "http://localhost:8000/build" -H "Content-Type: application/json" \
  -d '{"flavor": "dev", "platform": "all", "branch_name": "develop"}' &
```

**예상 결과**: 두 번째 빌드가 첫 번째 완료까지 대기

### 시나리오 3: PUB_CACHE 격리 검증
```bash
# 빌드 실행 중 PUB_CACHE 확인
BUILD_ID="dev-android-20250102-143022"
ls -la ~/ci-cd-workspace/builds/$BUILD_ID/pub_cache/global_packages/
```

**예상 결과**: melos 등 globally activated 패키지가 빌드별로 독립 설치됨

---

## 📊 모니터링

### 워크스페이스 통계
```bash
python monitor.py
```

출력 예시:
```
🔍 Flutter CI/CD Server - Workspace Statistics
======================================================================

📂 Workspace Root: /Users/user/ci-cd-workspace
📂 Builds Directory: /Users/user/ci-cd-workspace/builds

----------------------------------------------------------------------
📊 Build Caches
----------------------------------------------------------------------

총 5개 빌드 캐시

Build ID                                      Size      Age  Modified
----------------------------------------------------------------------
dev-android-20250102-143022                  2.5 GB      0d  2025-10-02 14:30:22
dev-ios-20250102-120000                      3.1 GB      0d  2025-10-02 12:00:00
...

----------------------------------------------------------------------
Total                                        10.3 GB

----------------------------------------------------------------------
💾 Disk Usage
----------------------------------------------------------------------

총 용량:     500.0 GB
사용 중:     250.0 GB (50.0%)
여유 공간:   250.0 GB
```

### 특정 빌드 상세 정보
```bash
python monitor.py dev-android-20250102-143022
```

---

## 🔧 트러블슈팅

### 문제 1: "Command not found: melos"
**해결**: PATH에 `$PUB_CACHE/bin`이 추가되어 있는지 확인

### 문제 2: 빌드가 큐에서 무한 대기
**해결**: 고아 락 파일 삭제
```bash
rm ~/ci-cd-workspace/queue_locks/*.lock
```

### 문제 3: 디스크 공간 부족
**즉시 조치**:
```bash
# 수동 정리
curl -X POST http://localhost:8000/cleanup

# 또는
python -c "from cleanup_scheduler import manual_cleanup; manual_cleanup(days=3)"
```

**장기 대책**:
- `CACHE_CLEANUP_DAYS` 환경변수를 3-5로 축소
- 디스크 모니터링 알림 설정

---

## 📈 예상 개선 효과

### 정량적 지표
- **빌드 충돌율**: 100% → 0%
- **동시 빌드 수**: 1개 → 무제한 (큐 기반 제어)
- **디스크 사용량**: 15GB → 50-100GB (빌드 수에 따라)

### 정성적 개선
- ✅ **안정성**: 버전 충돌 완전 제거
- ✅ **확장성**: 무제한 병렬 빌드
- ✅ **추적성**: 빌드별 독립 로그 및 아티팩트
- ✅ **재현성**: 빌드 환경 완전 격리

---

## 📚 참고 문서

- [PROCESS.md](./PROCESS.md) - 단계별 마이그레이션 진행 상황
- [README.md](./README.md) - 프로젝트 README
- [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) - API 문서
- [REQUIREMENTS.md](./REQUIREMENTS.md) - 요구사항 문서

---

## 🙏 마이그레이션 체크리스트

- [x] Phase 1: 의존성 추가 및 구조 설정
- [x] Phase 2: 큐 관리 시스템 구현
- [x] Phase 3: main.py 리팩토링
- [x] Phase 4: 빌드 스크립트 재작성
- [x] Phase 5: 캐시 정리 자동화
- [x] Phase 6: 모니터링 도구
- [x] Phase 7: 문서화

---

**마이그레이션 완료일**: 2025-10-02  
**담당**: AI Agent  
**상태**: ✅ 완료

