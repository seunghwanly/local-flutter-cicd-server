# 격리 환경 최적화 노트

## 🎯 제거된 불필요한 작업

### 1. `flutter clean` 제거 ✅

**위치:** `action/common/0_setup_isolated.sh`

**이전:**
```bash
fvm flutter clean
fvm exec melos run pub
```

**현재:**
```bash
# Note: flutter clean은 불필요 (격리된 환경 + git clean -fdx로 이미 깨끗함)
fvm exec melos run pub
```

**이유:**

1. **격리된 환경**: 각 빌드는 독립된 디렉토리 사용
   ```
   ~/ci-cd-workspace/builds/build-1/repo/  # 완전히 독립
   ~/ci-cd-workspace/builds/build-2/repo/  # 완전히 독립
   ```

2. **Git Clean**: 이미 `git clean -fdx`로 정리됨
   ```bash
   git reset --hard "origin/$BRANCH_NAME"
   git clean -fdx  # 모든 untracked 파일 제거
   ```

3. **첫 빌드**: 첫 clone이면 애초에 깨끗한 상태

---

## ⚡ 성능 개선 효과

### flutter clean 제거로 인한 이점

**시간 절약:**
- `flutter clean`: 평균 5-15초
- 대규모 프로젝트: 최대 30초

**디스크 I/O 감소:**
- build/ 디렉토리 삭제/재생성 불필요
- .dart_tool/ 재생성 불필요

**예상 개선:**
- 평균 빌드 시간: **5-15초 단축**
- 디스크 쓰기 작업: **~500MB 감소** (프로젝트 크기에 따라)

---

## 🔍 여전히 필요한 Clean 작업

### Git Clean (유지)

```bash
git reset --hard "origin/$BRANCH_NAME"
git clean -fdx
```

**이유:**
- 이전 빌드 실패로 인한 잔여 파일 제거
- Git tracked 상태를 원격과 동기화
- 로컬 수정사항 완전 제거

### 선택적 Clean (상황에 따라)

**언제 clean이 필요한가?**

1. **이전 공유 워킹디렉토리 방식**
   - 현재 런타임 경로에서는 제거됨
   - 과거에는 여러 빌드가 동일한 워킹 디렉토리를 재사용
   - → 그 구조에서는 `flutter clean` 유지 필요

2. **로컬 개발 환경**
   - 개발자가 수동으로 빌드하는 경우
   - → `flutter clean` 수동 실행

3. **격리 환경 (`action/common/*_isolated.sh`)**
   - 완전히 독립된 디렉토리
   - → `flutter clean` 불필요 ✅

---

## 📊 비교표

| 환경 | 디렉토리 | flutter clean | git clean | 이유 |
|------|---------|---------------|-----------|------|
| **레거시 (공유)** | `~/src/dev/project` | ✅ 필요 | ✅ 필요 | 동일 디렉토리 재사용 |
| **격리 (새로운)** | `~/ci-cd-workspace/builds/{id}/repo` | ❌ 불필요 | ✅ 필요 | 독립 디렉토리 + git 정리만 |
| **로컬 개발** | 개발자 로컬 | ✅ 수동 | ✅ 수동 | 필요시만 실행 |

---

## 🚀 추가 최적화 가능성

### 1. Git Clone 최적화

**현재:**
```bash
git clone "$REPO_URL" "$LOCAL_DIR"
```

**개선안:**
```bash
# Shallow clone (히스토리 최소화)
git clone --depth 1 --single-branch --branch "$BRANCH_NAME" "$REPO_URL" "$LOCAL_DIR"
```

**효과:**
- 클론 시간: 30-50% 단축
- 디스크 사용량: 50-70% 감소

**주의사항:**
- Git 히스토리가 필요한 작업 (git log, blame 등) 제한될 수 있음

### 2. Melos Bootstrap 캐싱

**현재:**
```bash
fvm exec melos run pub  # 매번 모든 패키지 다운로드
```

**개선안:**
```bash
# PUB_CACHE가 이미 격리되어 있으므로, 
# 동일 브랜치의 재빌드 시 캐시 활용 가능
```

**구현:**
- 동일 (branch, fvm_flavor, flavor)는 순차 실행되므로
- 이전 빌드의 PUB_CACHE를 재사용할 수 있음

### 3. Gradle 캐시 공유

**현재:**
```bash
GRADLE_USER_HOME=$BUILD_DIR/gradle_home  # 빌드별 독립
```

**개선안:**
```bash
# 동일 프로젝트의 모든 빌드가 Gradle 캐시 공유
GRADLE_USER_HOME=~/ci-cd-workspace/shared/gradle
```

**효과:**
- Android 빌드 시간: 20-40% 단축
- 디스크 사용량: 감소

**주의사항:**
- 서로 다른 Gradle 버전 간 충돌 가능성

---

## 📝 권장사항

### 즉시 적용 (완료) ✅

- [x] `flutter clean` 제거 (격리 스크립트)
- [x] 주석 추가 (이유 명시)

### 추가 검토 (선택사항)

- [ ] Git shallow clone 적용
- [ ] PUB_CACHE 재사용 전략
- [ ] Gradle 캐시 공유 전략

### 유지해야 할 것

- [x] `git clean -fdx` (Git 상태 정리)
- [x] 레거시 스크립트의 `flutter clean` (공유 디렉토리)

---

**작성일:** 2025-10-02  
**버전:** 1.0
