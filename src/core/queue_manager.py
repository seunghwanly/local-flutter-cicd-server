"""
Flutter CI/CD Server - Queue Manager Module

파일 기반 락을 사용한 빌드 큐 관리 시스템
- 동일 (branch, flutter_sdk_version, flavor) 조합: 순차 실행
- 서로 다른 조합: 병렬 실행
"""
import threading
from typing import Dict, Callable
from filelock import FileLock
from pathlib import Path
from .config import QUEUE_LOCKS_DIR
import logging

logger = logging.getLogger(__name__)

# 상수 정의
QUEUE_LOCK_TIMEOUT = 3600  # 1시간 (초)


class BuildQueueManager:
    """
    빌드 큐 관리자
    
    파일 락을 사용하여 동일한 큐 키를 가진 빌드는 순차적으로 실행되고,
    다른 큐 키를 가진 빌드는 병렬로 실행됩니다.
    """
    
    def __init__(self):
        """큐 관리자 초기화"""
        self.queues: Dict[str, threading.Lock] = {}
        self.locks_lock = threading.Lock()
        logger.info("🚀 Build Queue Manager initialized")
    
    def get_queue_key(self, branch_name: str, flutter_sdk_version: str, flavor: str) -> str:
        """
        큐 식별자 생성
        
        같은 큐 키를 가진 빌드는 순차적으로 실행됩니다.
        이는 동일한 git 저장소 디렉토리를 공유하는 것을 방지합니다.
        
        Args:
            branch_name: Git 브랜치 이름
            flutter_sdk_version: Flutter SDK 버전 (예: '3.29.3', 'stable', None)
            flavor: 빌드 환경 (dev, stage, prod)
            
        Returns:
            큐 키 문자열 (예: dev_develop_default, prod_main_3_29_3)
        """
        # 브랜치명 정규화 (슬래시, 점 등을 언더스코어로 변경)
        normalized_branch = (branch_name or "unknown").replace('/', '_').replace('.', '_').replace('-', '_')
        
        # Flutter SDK 버전 정규화
        normalized_version = (flutter_sdk_version or 'default').replace('.', '_').replace('-', '_')
        
        queue_key = f"{flavor}_{normalized_branch}_{normalized_version}"
        
        logger.debug(f"Generated queue key: {queue_key} (branch={branch_name}, flutter_sdk={flutter_sdk_version}, flavor={flavor})")
        
        return queue_key
    
    def get_lock_file(self, queue_key: str) -> Path:
        """
        큐별 락 파일 경로
        
        Args:
            queue_key: 큐 식별자
            
        Returns:
            락 파일 경로
        """
        return QUEUE_LOCKS_DIR / f"{queue_key}.lock"
    
    def execute_with_queue(
        self,
        queue_key: str,
        build_id: str,
        task: Callable,
        *args,
        **kwargs
    ):
        """
        큐에 따라 순차/병렬 실행
        
        같은 queue_key를 가진 빌드는 파일 락을 사용하여 순차 실행됩니다.
        다른 queue_key를 가진 빌드는 병렬로 실행됩니다.
        
        Args:
            queue_key: 큐 식별자
            build_id: 빌드 ID
            task: 실행할 작업 (Callable)
            *args: task에 전달할 위치 인자
            **kwargs: task에 전달할 키워드 인자
            
        Returns:
            task의 반환값
            
        Raises:
            FileLock timeout 시 Timeout 예외
        """
        lock_file = self.get_lock_file(queue_key)
        
        logger.info(f"[{build_id}] 🔒 Acquiring queue lock: {queue_key}")
        logger.info(f"[{build_id}] 📍 Lock file: {lock_file}")
        
        # 파일 기반 락으로 프로세스 간 동기화
        with FileLock(str(lock_file), timeout=QUEUE_LOCK_TIMEOUT):
            logger.info(f"[{build_id}] ✅ Queue lock acquired: {queue_key}")
            
            try:
                result = task(*args, **kwargs)
                logger.info(f"[{build_id}] 🎉 Task completed successfully")
                return result
                
            except Exception as e:
                logger.error(f"[{build_id}] ❌ Task failed: {str(e)}")
                raise
                
            finally:
                logger.info(f"[{build_id}] 🔓 Queue lock released: {queue_key}")


# 전역 인스턴스
queue_manager = BuildQueueManager()

