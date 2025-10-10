#!/usr/bin/env python3
"""
Flutter CI/CD Server - Main Entry Point

FastAPI 애플리케이션의 메인 진입점
"""
import sys
import os
import logging
from pathlib import Path

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def load_env_file(env_file_path: Path) -> bool:
    """
    .env 파일에서 환경변수를 안전하게 로드합니다.
    
    Args:
        env_file_path: .env 파일 경로
        
    Returns:
        로드 성공 여부
    """
    if not env_file_path.exists():
        logger.info(f"Environment file not found: {env_file_path}")
        return False
    
    try:
        loaded_count = 0
        with open(env_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    try:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # 값에서 따옴표 제거
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        
                        os.environ[key] = value
                        loaded_count += 1
                    except ValueError as e:
                        logger.warning(f"Invalid line {line_num} in {env_file_path}: {line} - {e}")
                        continue
        
        logger.info(f"Loaded {loaded_count} environment variables from {env_file_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to load environment file {env_file_path}: {e}")
        return False

# 환경변수 로드 (.env 파일이 있는 경우)
env_file = project_root / ".env"
load_env_file(env_file)

# FastAPI 애플리케이션 임포트
from .api import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)