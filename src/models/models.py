"""
Flutter CI/CD Server - API Models

Pydantic 모델 정의
"""
from typing import Dict, Optional, List
from pydantic import BaseModel, Field


class BuildRequest(BaseModel):
    """빌드 요청 모델"""
    flavor: str = Field(default="dev", description="Build flavor (dev, stage, prod)")
    platform: str = Field(default="all", description="Target platform (all, android, or ios)")
    build_name: Optional[str] = Field(default=None, description="Custom build name")
    build_number: Optional[str] = Field(default=None, description="Custom build number")
    branch_name: Optional[str] = Field(default=None, description="Git branch name to build from")
    fvm_flavor: Optional[str] = Field(default=None, description="FVM flavor key to select Flutter/CocoaPods versions")


class BuildStatusResponse(BaseModel):
    """빌드 상태 응답 모델"""
    build_id: str
    status: str
    started_at: str
    flavor: str
    platform: str
    fvm_flavor: Optional[str] = None
    branch_name: Optional[str] = None
    build_name: Optional[str] = None
    build_number: Optional[str] = None
    queue_key: Optional[str] = None
    processes: Dict
    progress: Dict
    logs: List[str]
    log_file_path: Optional[str] = None


class BuildSummary(BaseModel):
    """빌드 요약 모델"""
    build_id: str
    status: str
    started_at: str
    flavor: str
    platform: str
    fvm_flavor: Optional[str] = None
    branch_name: Optional[str] = None
    build_name: Optional[str] = None
    build_number: Optional[str] = None
    queue_key: Optional[str] = None


class BuildsResponse(BaseModel):
    """빌드 목록 응답 모델"""
    builds: List[BuildSummary]


class WebhookResponse(BaseModel):
    """Webhook 응답 모델"""
    status: str
    build_id: Optional[str] = None


class ManualBuildResponse(BaseModel):
    """수동 빌드 응답 모델"""
    status: str
    build_id: str


class RootResponse(BaseModel):
    """루트 응답 모델"""
    message: str


class CleanupResponse(BaseModel):
    """정리 응답 모델"""
    status: str
    message: str
