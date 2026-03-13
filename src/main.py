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
            pending_key = None
            pending_quote = None
            pending_value_lines = []

            for line_num, raw_line in enumerate(f, 1):
                line = raw_line.rstrip("\n")
                stripped = line.strip()

                if pending_key:
                    pending_value_lines.append(line)
                    if stripped.endswith(pending_quote):
                        pending_value_lines[-1] = pending_value_lines[-1][: pending_value_lines[-1].rfind(pending_quote)]
                        os.environ[pending_key] = "\n".join(pending_value_lines)
                        loaded_count += 1
                        pending_key = None
                        pending_quote = None
                        pending_value_lines = []
                    continue

                if not stripped or stripped.startswith('#') or '=' not in line:
                    continue

                try:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    if value.startswith('"') or value.startswith("'"):
                        quote_char = value[0]
                        if len(value) == 1 or not value.endswith(quote_char):
                            pending_key = key
                            pending_quote = quote_char
                            pending_value_lines = [value[1:]]
                            continue
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
for env_file in (project_root.parent / ".env", project_root / ".env"):
    if load_env_file(env_file):
        break

# FastAPI 애플리케이션 임포트
from .api import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
