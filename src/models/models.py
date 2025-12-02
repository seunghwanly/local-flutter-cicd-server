"""
Flutter CI/CD Server - API Models

Pydantic 모델 정의
"""
from typing import Dict, Optional, List
from pydantic import BaseModel, Field


class BuildRequest(BaseModel):
    """빌드 요청 모델"""
    flavor: str = Field(default="dev", description="flavor 설정: dev, stage, prod")
    platform: str = Field(default="all", description="platform 설정: all, android, ios")
    build_name: Optional[str] = Field(default=None, description="build name 설정 (e.g. 2.1.1)")
    build_number: Optional[str] = Field(default=None, description="build number 설정 (e.g. 623)")
    branch_name: Optional[str] = Field(default=None, description="branch name 설정 (e.g. develop, feature/update-version)")
    flutter_sdk_version: Optional[str] = Field(default=None, description="flutter sdk version 설정 (e.g. 3.35.4, stable)")
    gradle_version: Optional[str] = Field(default=None, description="gradle version 설정 (e.g. 8.10, 8.11)")
    cocoapods_version: Optional[str] = Field(default=None, description="cocoapods version 설정 (e.g. 1.15.2, 1.16.2)")
    fastlane_version: Optional[str] = Field(default=None, description="fastlane version 설정 (e.g. 2.228.0)")


class BuildStatusResponse(BaseModel):
    """빌드 상태 응답 모델"""
    build_id: str
    status: str
    started_at: str
    flavor: str
    platform: str
    flutter_sdk_version: Optional[str] = None
    gradle_version: Optional[str] = None
    cocoapods_version: Optional[str] = None
    fastlane_version: Optional[str] = None
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
    flutter_sdk_version: Optional[str] = None
    gradle_version: Optional[str] = None
    cocoapods_version: Optional[str] = None
    fastlane_version: Optional[str] = None
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
