"""In-memory and file-backed repository for build jobs."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from ..domain import BuildJob
from ..domain.builds import BuildStatus
from ..core.config import get_build_workspace, BUILDS_DIR

logger = logging.getLogger(__name__)


class BuildRepository:
    """Persistence boundary for build jobs (supports file-backed recovery)."""

    def __init__(self) -> None:
        self._jobs: Dict[str, BuildJob] = {}
        self._load_from_disk()

        # 백그라운드에서 주기적으로 활성 빌드 상태를 저장하는 스레드 실행
        self._persist_thread = threading.Thread(target=self._periodic_persist, daemon=True)
        self._persist_thread.start()

    def _load_from_disk(self) -> None:
        """서버 시작 시 .workspace/builds/ 내역을 스캔하여 복구합니다."""
        try:
            if not BUILDS_DIR.exists():
                return
            
            loaded_count = 0
            for build_dir in BUILDS_DIR.iterdir():
                if not build_dir.is_dir():
                    continue
                
                state_file = build_dir / "job_state.json"
                if state_file.exists():
                    try:
                        data = json.loads(state_file.read_text(encoding="utf-8"))
                        job = BuildJob.from_dict(data)
                        
                        # 강제 종료된 빌드 복구 처리 (실행 중이던 것은 FAILED로 변경)
                        if job.status in (BuildStatus.RUNNING, BuildStatus.PENDING):
                            job.status = BuildStatus.FAILED
                            job.logs.append(f"[{job.build_id}] ⚠️ Server restarted while build was running. Build marked as failed.")
                            
                        self._jobs[job.build_id] = job
                        loaded_count += 1
                    except Exception as e:
                        logger.error("Failed to load job state from %s: %s", state_file, e)
                        
            if loaded_count > 0:
                logger.info("Successfully recovered %d build jobs from workspace.", loaded_count)
                
        except Exception as e:
            logger.error("Failed to scan builds directory: %s", e)

    def _periodic_persist(self) -> None:
        """3초 주기로 변경될 가능성이 있는 빌드들의 상태를 디스크에 저장합니다."""
        while True:
            time.sleep(3.0)
            active_jobs = [j for j in self._jobs.values() if j.status in (BuildStatus.RUNNING, BuildStatus.PENDING)]
            for job in active_jobs:
                self._persist_to_disk(job)

    def _persist_to_disk(self, job: BuildJob) -> None:
        """단일 빌드 상태 직렬화 및 JSON 저장"""
        try:
            data = job.to_dict()
            build_dir = BUILDS_DIR / job.build_id
            build_dir.mkdir(parents=True, exist_ok=True)
            state_file = build_dir / "job_state.json"
            state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save job %s state to disk: %s", job.build_id, e)

    def save(self, job: BuildJob) -> None:
        self._jobs[job.build_id] = job
        self._persist_to_disk(job)

    def get(self, build_id: str) -> Optional[BuildJob]:
        return self._jobs.get(build_id)

    def list_all(self) -> List[BuildJob]:
        return list(self._jobs.values())

