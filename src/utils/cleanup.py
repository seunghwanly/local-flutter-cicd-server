"""
Flutter CI/CD Server - Cleanup Scheduler Module

오래된 빌드 캐시 및 고아 락 파일을 자동으로 정리하는 스케줄러
"""
import schedule
import time
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from ..core.config import BUILDS_DIR, QUEUE_LOCKS_DIR, get_cache_cleanup_days
import logging

logger = logging.getLogger(__name__)

# 상수 정의
ORPHANED_LOCK_HOURS = 24  # 고아 락 파일 판정 시간 (시간)
CLEANUP_SCHEDULE_TIME = "03:00"  # 정리 스케줄 시간
SCHEDULER_CHECK_INTERVAL = 60  # 스케줄러 확인 간격 (초)


def cleanup_old_builds(days: int = None):
    """
    오래된 빌드 캐시 삭제
    
    Args:
        days: 보관 기간 (일). None이면 환경변수 사용
    """
    if days is None:
        days = get_cache_cleanup_days()
    
    cutoff_date = datetime.now() - timedelta(days=days)
    deleted_count = 0
    freed_space = 0
    
    logger.info(f"🧹 Starting cleanup: removing builds older than {days} days")
    print(f"🧹 Starting cleanup: removing builds older than {days} days")
    
    try:
        for build_dir in BUILDS_DIR.iterdir():
            if not build_dir.is_dir():
                continue
            
            # 디렉토리 생성 시간 확인
            dir_mtime = datetime.fromtimestamp(build_dir.stat().st_mtime)
            
            if dir_mtime < cutoff_date:
                try:
                    # 디렉토리 크기 계산
                    dir_size = sum(f.stat().st_size for f in build_dir.rglob('*') if f.is_file())
                    
                    # 삭제
                    shutil.rmtree(build_dir)
                    
                    deleted_count += 1
                    freed_space += dir_size
                    size_mb = dir_size / 1024 / 1024
                    logger.info(f"🗑️ Deleted: {build_dir.name} ({size_mb:.1f} MB)")
                    print(f"🗑️ Deleted: {build_dir.name} ({size_mb:.1f} MB)")
                    
                except (OSError, PermissionError) as e:
                    logger.error(f"❌ Failed to delete {build_dir.name} (permission/OS error): {e}")
                    print(f"❌ Failed to delete {build_dir.name} (permission/OS error): {e}")
                except Exception as e:
                    logger.error(f"❌ Failed to delete {build_dir.name} (unexpected error): {e}")
                    print(f"❌ Failed to delete {build_dir.name} (unexpected error): {e}")
        
        freed_gb = freed_space / 1024 / 1024 / 1024
        logger.info(f"✅ Cleanup complete: {deleted_count} builds deleted, {freed_gb:.2f} GB freed")
        print(f"✅ Cleanup complete: {deleted_count} builds deleted, {freed_gb:.2f} GB freed")
        
    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        print(f"❌ Cleanup failed: {e}")


def cleanup_orphaned_locks():
    """
    고아 락 파일 정리
    
    24시간 이상 된 락 파일은 고아로 간주하여 삭제합니다.
    """
    deleted_count = 0
    
    logger.info("🧹 Checking for orphaned lock files...")
    
    try:
        for lock_file in QUEUE_LOCKS_DIR.glob("*.lock"):
            try:
                # 고아 락 파일 판정
                lock_age = datetime.now() - datetime.fromtimestamp(lock_file.stat().st_mtime)
                
                if lock_age > timedelta(hours=ORPHANED_LOCK_HOURS):
                    lock_file.unlink()
                    deleted_count += 1
                    logger.info(f"🗑️ Deleted orphaned lock: {lock_file.name}")
                    print(f"🗑️ Deleted orphaned lock: {lock_file.name}")
                    
            except (OSError, PermissionError) as e:
                logger.error(f"❌ Failed to delete lock {lock_file.name} (permission/OS error): {e}")
                print(f"❌ Failed to delete lock {lock_file.name} (permission/OS error): {e}")
            except Exception as e:
                logger.error(f"❌ Failed to delete lock {lock_file.name} (unexpected error): {e}")
                print(f"❌ Failed to delete lock {lock_file.name} (unexpected error): {e}")
        
        if deleted_count > 0:
            logger.info(f"✅ Removed {deleted_count} orphaned locks")
            print(f"✅ Removed {deleted_count} orphaned locks")
        else:
            logger.info("✅ No orphaned locks found")
            
    except Exception as e:
        logger.error(f"❌ Lock cleanup failed: {e}")
        print(f"❌ Lock cleanup failed: {e}")


def start_cleanup_scheduler(cleanup_days: int = None):
    """
    정리 스케줄러 시작
    
    매일 새벽 3시에 빌드 캐시 및 락 파일을 정리합니다.
    
    Args:
        cleanup_days: 빌드 캐시 보관 기간 (일). None이면 환경변수 사용
    """
    if cleanup_days is None:
        cleanup_days = get_cache_cleanup_days()
    
    # 매일 정리 스케줄 설정
    schedule.every().day.at(CLEANUP_SCHEDULE_TIME).do(cleanup_old_builds, days=cleanup_days)
    schedule.every().day.at(CLEANUP_SCHEDULE_TIME).do(cleanup_orphaned_locks)
    
    logger.info(f"🕒 Cleanup scheduler started")
    logger.info(f"   - Daily cleanup at {CLEANUP_SCHEDULE_TIME}")
    logger.info(f"   - Keeping {cleanup_days} days of build caches")
    print(f"🕒 Cleanup scheduler started (daily at {CLEANUP_SCHEDULE_TIME}, keeping {cleanup_days} days)")
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(SCHEDULER_CHECK_INTERVAL)
        except Exception as e:
            logger.error(f"❌ Scheduler error: {e}")
            print(f"❌ Scheduler error: {e}")
            time.sleep(SCHEDULER_CHECK_INTERVAL)


def manual_cleanup(days: int = None):
    """
    수동 정리 실행
    
    Args:
        days: 보관 기간 (일). None이면 환경변수 사용
    """
    logger.info("🧹 Manual cleanup triggered")
    print("🧹 Manual cleanup triggered")
    
    cleanup_old_builds(days)
    cleanup_orphaned_locks()
    
    logger.info("✅ Manual cleanup completed")
    print("✅ Manual cleanup completed")

