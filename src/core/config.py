"""
Flutter CI/CD Server - Configuration Module

빌드별 완전 격리된 환경을 제공하는 설정 모듈
"""
import os
from pathlib import Path
import logging
import shutil

logger = logging.getLogger(__name__)

# 상수 정의
SSH_KEY_RESTRICTIVE_PERMS = 0o077

# 기본 경로 설정 (항상 절대 경로 사용)
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", os.path.expanduser("~/ci-cd-workspace"))).resolve()
BUILDS_DIR = (WORKSPACE_ROOT / "builds").resolve()
QUEUE_LOCKS_DIR = (WORKSPACE_ROOT / "queue_locks").resolve()

# 워크스페이스 초기화
BUILDS_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_LOCKS_DIR.mkdir(parents=True, exist_ok=True)

logger.info(f"📂 Workspace root: {WORKSPACE_ROOT}")
logger.info(f"📂 Builds directory: {BUILDS_DIR}")
logger.info(f"🔒 Queue locks directory: {QUEUE_LOCKS_DIR}")


def setup_git_credentials(build_workspace: Path, env: dict):
    """Git 자격증명 설정 (SSH 또는 HTTPS)"""
    home_dir = Path.home()
    
    # 1. HOME 환경변수 확인 (필수)
    if "HOME" not in env:
        env["HOME"] = str(home_dir)
    
    # GITHUB_TOKEN이 있으면 HTTPS 모드
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        # .git-credentials 파일 생성
        git_credentials = build_workspace / ".git-credentials"
        git_credentials.write_text(f"https://{github_token}@github.com\n")
        git_credentials.chmod(0o600)
        
        # Git credential helper 설정
        gitconfig = build_workspace / ".gitconfig"
        gitconfig.write_text(f"""[credential]
    helper = store --file={git_credentials}
""")
        env["GIT_CONFIG_GLOBAL"] = str(gitconfig)
        print(f"✅ HTTPS credentials configured using GITHUB_TOKEN")
        logger.info(f"✅ HTTPS credentials configured using GITHUB_TOKEN")
    else:
        # SSH 모드: 기존 SSH 설정 로직
        # 2. SSH_AUTH_SOCK 확인 및 전달
        ssh_auth_sock = os.environ.get("SSH_AUTH_SOCK")
        if ssh_auth_sock:
            env["SSH_AUTH_SOCK"] = ssh_auth_sock
            print(f"✅ SSH_AUTH_SOCK: {ssh_auth_sock}")
            logger.info(f"✅ SSH_AUTH_SOCK: {ssh_auth_sock}")
        else:
            print(f"⚠️ SSH_AUTH_SOCK not found - SSH Agent may not be running")
            logger.warning(f"⚠️ SSH_AUTH_SOCK not found - SSH Agent may not be running")
        
        # 3. SSH 설정 파일 명시적 지정
        ssh_config = home_dir / ".ssh" / "config"
        if ssh_config.exists():
            # GIT_SSH_COMMAND로 SSH 옵션 명시
            env["GIT_SSH_COMMAND"] = f"ssh -F {ssh_config} -o StrictHostKeyChecking=no"
            print(f"✅ SSH config: {ssh_config}")
            logger.info(f"✅ SSH config: {ssh_config}")
        else:
            # 기본 SSH 명령
            env["GIT_SSH_COMMAND"] = "ssh -o StrictHostKeyChecking=no"
        
        # 4. .gitconfig 복사 (선택적이지만 권장)
        gitconfig_src = home_dir / ".gitconfig"
        if gitconfig_src.exists():
            gitconfig_dest = build_workspace / ".gitconfig"
            shutil.copy2(gitconfig_src, gitconfig_dest)
            env["GIT_CONFIG_GLOBAL"] = str(gitconfig_dest)
            print(f"✅ Copied .gitconfig")
            logger.info(f"✅ Copied .gitconfig")
        
        # 5. SSH 키 권한 확인
        ssh_key = home_dir / ".ssh" / "id_rsa"
        if ssh_key.exists():
            key_stat = ssh_key.stat()
            if key_stat.st_mode & SSH_KEY_RESTRICTIVE_PERMS:
                print(f"⚠️ Warning: SSH key has too open permissions")
                logger.warning(f"⚠️ Warning: SSH key has too open permissions")
            print(f"✅ SSH key found: {ssh_key}")
            logger.info(f"✅ SSH key found: {ssh_key}")
        else:
            print(f"❌ SSH key not found: {ssh_key}")
            logger.error(f"❌ SSH key not found: {ssh_key}")


def get_build_workspace(build_id: str) -> Path:
    """
    빌드별 독립 작업 공간 경로 반환
    
    Args:
        build_id: 빌드 고유 ID (예: dev-android-20250102-143022)
        
    Returns:
        빌드 작업 공간 경로
    """
    return BUILDS_DIR / build_id


def get_shared_cache_dir() -> Path:
    """
    버전별 공유 캐시 디렉토리를 반환합니다.
    
    Returns:
        공유 캐시 루트 디렉토리 경로
    """
    shared = Path.home() / "ci-cd-workspace" / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    return shared


def get_version_cache_dirs(flutter_version: str = None, gradle_version: str = None, cocoapods_version: str = None) -> dict:
    """
    버전별 공유 캐시 디렉토리를 생성하고 반환합니다.
    
    동일한 버전을 사용하는 빌드들이 캐시를 공유하여 다운로드 시간과 디스크 사용량을 절감합니다.
    
    Args:
        flutter_version: Flutter SDK 버전 (예: "3.35.4")
        gradle_version: Gradle 버전 (예: "8.10")
        cocoapods_version: CocoaPods 버전 (예: "1.14.3")
        
    Returns:
        버전별 캐시 디렉토리 경로 dict:
        - pub_cache: Flutter/Pub 패키지 캐시
        - git_cache: Git 의존성 캐시 (전역 공유)
        - gradle_cache: Gradle 캐시
        - gem_cache: Ruby gems 캐시
        - cocoapods_cache: CocoaPods 캐시
        - deriveddata_cache: Xcode DerivedData 캐시
    """
    shared = get_shared_cache_dir()
    result = {}
    
    # Flutter/Pub 캐시 (버전별)
    if flutter_version:
        pub_cache = shared / "pub" / flutter_version
        pub_cache.mkdir(parents=True, exist_ok=True)
        result['pub_cache'] = pub_cache
    
    # Git 의존성 캐시 (전역 공유, 버전 무관)
    git_cache = shared / "pub" / "git"
    git_cache.mkdir(parents=True, exist_ok=True)
    result['git_cache'] = git_cache
    
    # Gradle 캐시 (버전별)
    if gradle_version:
        gradle_cache = shared / "gradle" / gradle_version
        gradle_cache.mkdir(parents=True, exist_ok=True)
        result['gradle_cache'] = gradle_cache
    
    # Ruby Gems 캐시 (CocoaPods 버전별)
    if cocoapods_version:
        gem_cache = shared / "gems" / f"cocoapods-{cocoapods_version}"
        gem_cache.mkdir(parents=True, exist_ok=True)
        result['gem_cache'] = gem_cache
        
        # CocoaPods 캐시도 버전별로
        cocoapods_cache = shared / "cocoapods" / cocoapods_version
        cocoapods_cache.mkdir(parents=True, exist_ok=True)
        result['cocoapods_cache'] = cocoapods_cache
        
        # DerivedData 캐시 (CocoaPods 버전별)
        deriveddata_cache = shared / "deriveddata" / cocoapods_version
        deriveddata_cache.mkdir(parents=True, exist_ok=True)
        result['deriveddata_cache'] = deriveddata_cache
    
    return result


def warmup_git_dependencies(pub_cache_dir: Path, build_id: str = None) -> bool:
    """
    시스템의 pub cache에서 git 의존성 복사 또는 심볼릭 링크 생성
    
    격리된 PUB_CACHE에서 처음 git 의존성을 clone할 때 발생하는
    bare repository 초기화 실패를 방지합니다.
    
    Args:
        pub_cache_dir: 격리된 pub cache 디렉토리
        build_id: 빌드 ID (로깅용, 선택사항)
        
    Returns:
        Git 캐시 설정 성공 여부
    """
    system_pub_cache = Path.home() / ".pub-cache"
    system_git_cache = system_pub_cache / "git"
    target_git_cache = pub_cache_dir / "git"
    
    log_prefix = f"[{build_id}] " if build_id else ""
    
    if system_git_cache.exists() and not target_git_cache.exists():
        try:
            # 심볼릭 링크로 공유 (복사 대신)
            target_git_cache.symlink_to(system_git_cache)
            logger.info(f"{log_prefix}🔗 Git cache linked to system: {system_git_cache}")
            print(f"{log_prefix}🔗 Git cache linked to system")
            
            # 캐시 항목 수 확인
            cache_items = list(system_git_cache.glob('cache/*'))
            if cache_items:
                logger.info(f"{log_prefix}✅ Git cache warmed up: {len(cache_items)} repositories")
                print(f"{log_prefix}✅ Git cache contains {len(cache_items)} repositories")
            else:
                logger.warning(f"{log_prefix}⚠️ System git cache is empty. First build may initialize git dependencies.")
                print(f"{log_prefix}⚠️ System git cache is empty")
            
            return True
        except Exception as e:
            logger.error(f"{log_prefix}❌ Failed to link git cache: {str(e)}")
            print(f"{log_prefix}❌ Failed to link git cache: {str(e)}")
            return False
    elif target_git_cache.exists():
        logger.info(f"{log_prefix}✅ Git cache already exists")
        return True
    else:
        logger.warning(f"{log_prefix}⚠️ System git cache not found: {system_git_cache}")
        print(f"{log_prefix}⚠️ System git cache not found. First build will initialize git dependencies.")
        return False


def _create_symlink_or_directory(target_path: Path, source_path: Path = None, build_id: str = None) -> None:
    """
    심볼릭 링크 또는 디렉토리를 안전하게 생성합니다.
    
    Args:
        target_path: 생성할 경로
        source_path: 심볼릭 링크 대상 경로 (None이면 일반 디렉토리)
        build_id: 빌드 ID (로깅용)
    """
    log_prefix = f"[{build_id}] " if build_id else ""
    
    # 기존 디렉토리/링크 제거
    if target_path.exists() or target_path.is_symlink():
        try:
            if target_path.is_symlink():
                target_path.unlink()
            elif target_path.is_dir():
                shutil.rmtree(target_path)
        except Exception as e:
            logger.warning(f"{log_prefix}Failed to remove existing path {target_path}: {e}")
    
    # 새로 생성
    try:
        if source_path:
            target_path.symlink_to(source_path)
            logger.info(f"{log_prefix}🔗 Linked {target_path.name} to {source_path}")
        else:
            target_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"{log_prefix}📁 Created directory {target_path.name}")
    except Exception as e:
        logger.error(f"{log_prefix}Failed to create {target_path}: {e}")
        raise

def get_isolated_env(build_id: str, flutter_version: str = None, gradle_version: str = None, cocoapods_version: str = None) -> dict:
    """
    완전히 격리된 환경변수 생성
    
    각 빌드는 독립된 디렉토리 구조를 가지며:
    - repo/: Git 저장소 클론
    - pub_cache/: Dart/Flutter 패키지 캐시 → 버전별 공유 캐시에 심볼릭 링크
    - gradle_home/: Android Gradle 캐시 → 버전별 공유 캐시에 심볼릭 링크
    - gem_home/: Ruby gems (CocoaPods 포함) → 버전별 공유 캐시에 심볼릭 링크
    - cocoapods_cache/: CocoaPods 캐시 → 버전별 공유 캐시에 심볼릭 링크
    - deriveddata_cache/: Xcode DerivedData 캐시 → 버전별 공유 캐시에 심볼릭 링크
    - pub_cache/git/: Git 의존성은 전역 공유
    
    Args:
        build_id: 빌드 고유 ID
        flutter_version: Flutter SDK 버전 (optional, 공유 캐시 사용)
        gradle_version: Gradle 버전 (optional, 공유 캐시 사용)
        cocoapods_version: CocoaPods 버전 (optional, 공유 캐시 사용)
        
    Returns:
        격리된 환경 정보 딕셔너리:
        - env: 환경변수 dict
        - repo_dir: Git 저장소 경로
        - pub_cache_dir: PUB_CACHE 경로
        - gradle_home_dir: GRADLE_USER_HOME 경로
        - gem_home_dir: GEM_HOME 경로
        - cocoapods_cache_dir: CP_HOME_DIR 경로
        - deriveddata_cache_dir: DERIVED_DATA_PATH 경로
    """
    workspace = get_build_workspace(build_id)
    
    # Git 저장소는 항상 독립
    repo_dir = (workspace / "repo").resolve()
    repo_dir.mkdir(parents=True, exist_ok=True)
    
    # 버전별 공유 캐시 사용 여부 결정
    use_shared_cache = flutter_version or gradle_version or cocoapods_version
    shared_caches = {}
    
    if use_shared_cache:
        # 버전별 공유 캐시 생성
        shared_caches = get_version_cache_dirs(
            flutter_version=flutter_version,
            gradle_version=gradle_version,
            cocoapods_version=cocoapods_version
        )
        
        # 심볼릭 링크로 공유 캐시 연결
        pub_cache_dir = (workspace / "pub_cache").resolve()
        gradle_home_dir = (workspace / "gradle_home").resolve()
        gem_home_dir = (workspace / "gem_home").resolve()
        cocoapods_cache_dir = (workspace / "cocoapods_cache").resolve()
        deriveddata_cache_dir = (workspace / "deriveddata_cache").resolve()
        
        # 공유 캐시 디렉토리 생성
        if flutter_version and 'pub_cache' in shared_caches:
            _create_symlink_or_directory(pub_cache_dir, shared_caches['pub_cache'], build_id)
        else:
            _create_symlink_or_directory(pub_cache_dir, None, build_id)
        
        if gradle_version and 'gradle_cache' in shared_caches:
            _create_symlink_or_directory(gradle_home_dir, shared_caches['gradle_cache'], build_id)
        else:
            _create_symlink_or_directory(gradle_home_dir, None, build_id)
        
        if cocoapods_version and 'gem_cache' in shared_caches:
            _create_symlink_or_directory(gem_home_dir, shared_caches['gem_cache'], build_id)
        else:
            _create_symlink_or_directory(gem_home_dir, None, build_id)
        
        if cocoapods_version and 'cocoapods_cache' in shared_caches:
            _create_symlink_or_directory(cocoapods_cache_dir, shared_caches['cocoapods_cache'], build_id)
        else:
            _create_symlink_or_directory(cocoapods_cache_dir, None, build_id)
        
        if cocoapods_version and 'deriveddata_cache' in shared_caches:
            _create_symlink_or_directory(deriveddata_cache_dir, shared_caches['deriveddata_cache'], build_id)
        else:
            _create_symlink_or_directory(deriveddata_cache_dir, None, build_id)
    else:
        # 버전 정보 없으면 독립 디렉토리 생성 (기존 동작)
        pub_cache_dir = (workspace / "pub_cache").resolve()
        gradle_home_dir = (workspace / "gradle_home").resolve()
        gem_home_dir = (workspace / "gem_home").resolve()
        cocoapods_cache_dir = (workspace / "cocoapods_cache").resolve()
        deriveddata_cache_dir = (workspace / "deriveddata_cache").resolve()
        
        pub_cache_dir.mkdir(parents=True, exist_ok=True)
        gradle_home_dir.mkdir(parents=True, exist_ok=True)
        gem_home_dir.mkdir(parents=True, exist_ok=True)
        cocoapods_cache_dir.mkdir(parents=True, exist_ok=True)
        deriveddata_cache_dir.mkdir(parents=True, exist_ok=True)
    
    # 환경변수 복사
    env = os.environ.copy()
    
    # 핵심 환경변수 명시적 설정 (절대 경로 사용)
    env["PUB_CACHE"] = str(pub_cache_dir)
    env["GRADLE_USER_HOME"] = str(gradle_home_dir)
    env["GEM_HOME"] = str(gem_home_dir)
    env["GEM_PATH"] = str(gem_home_dir)
    env["CP_HOME_DIR"] = str(cocoapods_cache_dir)
    env["DERIVED_DATA_PATH"] = str(deriveddata_cache_dir)
    env["PATH"] = f"{gem_home_dir / 'bin'}:{pub_cache_dir / 'bin'}:{env.get('PATH', '/usr/local/bin:/usr/bin:/bin')}"
    env["HOME"] = str(Path.home().resolve())  # 명시적 HOME 설정 (절대 경로)
    
    # Git 자격증명 설정
    setup_git_credentials(workspace, env)
    
    # Git 의존성 캐시 워밍업 (공유 캐시 또는 시스템 캐시 사용)
    if use_shared_cache and 'git_cache' in shared_caches:
        # 공유 git 캐시를 PUB_CACHE 내부에 링크
        git_link = pub_cache_dir / "git"
        if not git_link.exists() and not git_link.is_symlink():
            git_link.symlink_to(shared_caches['git_cache'])
            logger.info(f"[{build_id}] 🔗 Git cache linked to shared: {shared_caches['git_cache']}")
    else:
        # 레거시: 시스템 캐시 사용
        warmup_git_dependencies(pub_cache_dir, build_id)
    
    # 디버그 정보 출력
    print(f"🔍 Environment debug:")
    print(f"   HOME: {env.get('HOME')}")
    print(f"   SSH_AUTH_SOCK: {env.get('SSH_AUTH_SOCK', 'NOT SET')}")
    print(f"   GIT_SSH_COMMAND: {env.get('GIT_SSH_COMMAND', 'NOT SET')}")
    print(f"   PUB_CACHE: {env.get('PUB_CACHE')}")
    
    logger.info(f"[{build_id}] 🔒 Isolated environment created:")
    logger.info(f"[{build_id}]   - Repo: {repo_dir}")
    logger.info(f"[{build_id}]   - PUB_CACHE: {pub_cache_dir}")
    logger.info(f"[{build_id}]   - GRADLE_HOME: {gradle_home_dir}")
    logger.info(f"[{build_id}]   - GEM_HOME: {gem_home_dir}")
    logger.info(f"[{build_id}]   - CP_HOME_DIR: {cocoapods_cache_dir}")
    logger.info(f"[{build_id}]   - DERIVED_DATA_PATH: {deriveddata_cache_dir}")
    logger.info(f"[{build_id}]   - HOME: {env.get('HOME')}")
    logger.info(f"[{build_id}]   - SSH_AUTH_SOCK: {env.get('SSH_AUTH_SOCK', 'NOT SET')}")
    
    return {
        "env": env,
        "repo_dir": str(repo_dir),
        "pub_cache_dir": str(pub_cache_dir),
        "gradle_home_dir": str(gradle_home_dir),
        "gem_home_dir": str(gem_home_dir),
        "cocoapods_cache_dir": str(cocoapods_cache_dir),
        "deriveddata_cache_dir": str(deriveddata_cache_dir),
    }


def get_cache_cleanup_days() -> int:
    """
    캐시 정리 보관 기간 (일)
    
    Returns:
        보관 기간 (기본: 7일)
    """
    return int(os.environ.get("CACHE_CLEANUP_DAYS", 7))


def get_max_parallel_builds() -> int:
    """
    최대 병렬 빌드 수
    
    Returns:
        최대 병렬 빌드 수 (기본: 3)
    """
    return int(os.environ.get("MAX_PARALLEL_BUILDS", 3))

