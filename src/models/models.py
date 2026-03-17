"""Pydantic models for API IO."""

from typing import Dict, Optional, List, Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator


class BuildRequest(BaseModel):
    """빌드 요청 모델"""
    flavor: Literal["dev", "stage", "prod"] = Field(
        default="dev", 
        description="flavor 설정: dev, stage, prod",
        example="dev"
    )
    platform: Literal["all", "android", "ios"] = Field(
        default="all", 
        description="platform 설정: all, android, ios",
        example="all"
    )
    build_name: Optional[str] = Field(
        default=None, 
        description="build name 설정 (e.g. 2.1.1)",
        example="2.1.1"
    )
    build_number: Optional[str] = Field(
        default=None, 
        description="build number 설정 (e.g. 623)",
        example="623"
    )
    branch_name: Optional[str] = Field(
        default=None, 
        description="branch name 설정 (e.g. develop, feature/update-version)",
        example="develop"
    )

    @field_validator(
        "build_name",
        "build_number",
        "branch_name",
        mode="before",
    )
    @classmethod
    def normalize_blank_strings(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "flavor": "dev",
                "platform": "all",
                "build_name": "2.1.1",
                "build_number": "623",
                "branch_name": "develop",
            }
        }
    )


class BuildStatusResponse(BaseModel):
    """빌드 상태 응답 모델"""
    build_id: str
    status: str
    started_at: str
    flavor: str
    platform: str
    trigger_source: str = "manual"
    trigger_event_id: Optional[str] = None
    flutter_sdk_version: Optional[str] = None
    resolved_flutter_sdk_version: Optional[str] = None
    gradle_version: Optional[str] = None
    cocoapods_version: Optional[str] = None
    fastlane_version: Optional[str] = None
    branch_name: Optional[str] = None
    build_name: Optional[str] = None
    build_number: Optional[str] = None
    cancel_reason: Optional[str] = None
    cancel_requested_at: Optional[str] = None
    canceled_at: Optional[str] = None
    queue_key: Optional[str] = None
    platform_statuses: Dict = Field(default_factory=dict)
    processes: Dict
    progress: Dict
    stages: List[Dict] = Field(default_factory=list)
    logs: List[str]
    log_file_path: Optional[str] = None


class BuildSummary(BaseModel):
    """빌드 요약 모델"""
    build_id: str
    status: str
    started_at: str
    flavor: str
    platform: str
    trigger_source: str = "manual"
    trigger_event_id: Optional[str] = None
    flutter_sdk_version: Optional[str] = None
    resolved_flutter_sdk_version: Optional[str] = None
    gradle_version: Optional[str] = None
    cocoapods_version: Optional[str] = None
    fastlane_version: Optional[str] = None
    branch_name: Optional[str] = None
    build_name: Optional[str] = None
    build_number: Optional[str] = None
    cancel_reason: Optional[str] = None
    cancel_requested_at: Optional[str] = None
    canceled_at: Optional[str] = None
    queue_key: Optional[str] = None
    platform_statuses: Dict = Field(default_factory=dict)
    stages: List[Dict] = Field(default_factory=list)


class BuildsResponse(BaseModel):
    """빌드 목록 응답 모델"""
    builds: List[BuildSummary]


class ActionResponse(BaseModel):
    """외부 action 트리거 응답 모델"""
    status: str
    build_id: Optional[str] = None


class ShorebirdWebhookMetadata(BaseModel):
    """Shorebird webhook metadata payload."""

    flavor: Optional[str] = Field(
        default=None,
        description="빌드 flavor. dev, stg, stage, prd, prod 같은 값을 지원",
        example="stg",
    )
    build_name: Optional[str] = Field(
        default=None,
        description="빌드 이름",
        example="2.2.1",
    )
    build_number: Optional[str] = Field(
        default=None,
        description="빌드 번호",
        example="689",
    )

    model_config = ConfigDict(extra="allow")


class ShorebirdWebhookRequest(BaseModel):
    """GitHub-delivered Shorebird webhook payload for docs and validation."""

    ref_type: str = Field(
        description="GitHub ref 타입. shorebird webhook은 tag 여야 함",
        example="tag",
    )
    ref: str = Field(
        description="생성된 태그 이름. build_name fallback으로 사용",
        example="2.2.1",
    )
    payload: Optional[ShorebirdWebhookMetadata] = Field(
        default=None,
        description="권장 메타데이터 컨테이너",
    )
    inputs: Optional[ShorebirdWebhookMetadata] = Field(
        default=None,
        description="대체 메타데이터 컨테이너",
    )
    client_payload: Optional[ShorebirdWebhookMetadata] = Field(
        default=None,
        description="대체 메타데이터 컨테이너",
    )
    flavor: Optional[str] = Field(
        default=None,
        description="top-level flavor override",
        example="prd",
    )
    build_name: Optional[str] = Field(
        default=None,
        description="top-level build name override",
        example="2.2.1",
    )
    build_number: Optional[str] = Field(
        default=None,
        description="top-level build number override",
        example="689",
    )

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "ref_type": "tag",
                "ref": "2.2.1",
                "payload": {
                    "flavor": "stg",
                    "build_name": "2.2.1",
                    "build_number": "689",
                },
            }
        },
    )


class ManualBuildResponse(BaseModel):
    """수동 빌드 응답 모델"""
    status: str
    build_id: str


class CancelBuildResponse(BaseModel):
    """빌드 취소 응답 모델"""
    status: str
    build_id: str
    message: str


class RootResponse(BaseModel):
    """루트 응답 모델"""
    message: str


class CleanupResponse(BaseModel):
    """정리 응답 모델"""
    status: str
    message: str


class DiagnosticItem(BaseModel):
    feature: str
    ready: bool
    missing: List[str]
    details: Dict[str, str] = Field(default_factory=dict)


class DiagnosticsResponse(BaseModel):
    diagnostics: Dict[str, DiagnosticItem]
