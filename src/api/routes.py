"""FastAPI routes."""

from typing import Optional

from fastapi import FastAPI, Request, Header, HTTPException, Form
from fastapi.responses import HTMLResponse
from pathlib import Path
import os
import threading
from pydantic import ValidationError

from ..models import (
    ActionResponse, BuildRequest, BuildStatusResponse, BuildsResponse,
    ManualBuildResponse, RootResponse, CleanupResponse, DiagnosticsResponse
)
from ..application import ConfigDiagnostics
from ..services.build_service import build_service
from ..services.action_service import github_action_service, shorebird_action_service
from ..core.config import get_cache_cleanup_days
from ..utils.cleanup import start_cleanup_scheduler, manual_cleanup


def create_app() -> FastAPI:
    """FastAPI 애플리케이션 생성"""
    diagnostics = ConfigDiagnostics()
    app = FastAPI(
        title="Flutter CI/CD Server API",
        description="Flutter 애플리케이션의 CI/CD 파이프라인을 관리하는 서버 API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    @app.get("/", response_model=RootResponse, tags=["Health Check"])
    async def root():
        """
        서버 상태 확인
        
        Flutter CI/CD 서버가 정상적으로 실행 중인지 확인합니다.
        """
        return {"message": "👋 Flutter CI/CD Container is running!"}

    @app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
    async def dashboard():
        """
        웹 대시보드 화면
        
        로컬 서버의 빌드 상태와 로그를 실시간으로 확인할 수 있는 대시보드 UI를 제공합니다.
        """
        dashboard_path = Path(__file__).parent / "dashboard.html"
        try:
            with open(dashboard_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Dashboard UI file not found")


    @app.get("/diagnostics", response_model=DiagnosticsResponse, tags=["Health Check"])
    async def runtime_diagnostics():
        results = diagnostics.get_runtime_diagnostics()
        return {
            "diagnostics": {
                name: {
                    "feature": result.feature,
                    "ready": result.ready,
                    "missing": result.missing,
                    "details": result.details,
                }
                for name, result in results.items()
            }
        }
    
    @app.get("/build/{build_id}", response_model=BuildStatusResponse, tags=["Build Status"])
    async def get_build_status(build_id: str):
        """
        빌드 상태 조회
        
        특정 빌드 ID의 현재 상태와 로그를 조회합니다.
        
        - **build_id**: 조회할 빌드의 고유 ID
        """
        build_status = build_service.get_build_status(build_id)
        if not build_status:
            raise HTTPException(status_code=404, detail="Build not found")
        
        return build_status
    
    @app.get("/builds", response_model=BuildsResponse, tags=["Build Status"])
    async def list_builds():
        """
        빌드 목록 조회
        
        모든 빌드의 현재 상태를 조회합니다.
        """
        builds = build_service.list_builds()
        return {"builds": builds}
    
    @app.post("/github-action/build", response_model=ActionResponse, tags=["GitHub Actions"])
    async def handle_github_build_action(
        request: Request,
        x_hub_signature_256: str = Header(None, description="GitHub webhook signature"),
        x_hub_signature: str = Header(None, description="GitHub webhook signature (sha1)"),
        x_github_event: str = Header(None, description="GitHub event type"),
        x_github_delivery: str = Header(None, description="GitHub delivery id"),
    ):
        """
        GitHub build action 처리
        
        GitHub에서 전송되는 일반 build action 이벤트를 처리합니다.
        
        지원하는 이벤트:
        - PR이 release/dev* 브랜치에 머지될 때 (dev 빌드 트리거)
        - 태그가 생성될 때 (prod 빌드 트리거)
        
        참고:
        - stage 빌드는 자동 트리거가 아닌 수동 트리거로 사용합니다.
        """
        action_diagnostics = diagnostics.get_github_action_diagnostics()
        if not action_diagnostics.ready:
            raise HTTPException(
                status_code=503,
                detail=f"GitHub action is not configured. Missing: {', '.join(action_diagnostics.missing)}",
            )

        body = await request.body()

        if not github_action_service.verify_signature(body, x_hub_signature_256, x_hub_signature):
            raise HTTPException(status_code=403, detail="Invalid signature")

        payload = await request.json()
        result = github_action_service.handle(payload, x_github_event, x_github_delivery)
        return result

    @app.post("/github-action/shorebird", response_model=ActionResponse, tags=["GitHub Actions"])
    async def handle_github_shorebird_action(
        request: Request,
        x_hub_signature_256: str = Header(None, description="GitHub webhook signature"),
        x_hub_signature: str = Header(None, description="GitHub webhook signature (sha1)"),
        x_github_event: str = Header(None, description="GitHub event type"),
        x_github_delivery: str = Header(None, description="GitHub delivery id"),
    ):
        """
        GitHub Shorebird action 처리

        GitHub가 전달한 Shorebird patch 이벤트를 공통 빌드 파이프라인으로 전달합니다.
        """
        action_diagnostics = diagnostics.get_shorebird_action_diagnostics()
        if not action_diagnostics.ready:
            raise HTTPException(
                status_code=503,
                detail=f"Shorebird action is not configured. Missing: {', '.join(action_diagnostics.missing)}",
            )

        body = await request.body()
        if not shorebird_action_service.verify_signature(body, x_hub_signature_256, x_hub_signature):
            raise HTTPException(status_code=403, detail="Invalid signature")

        payload = await request.json()
        return shorebird_action_service.handle(payload, x_github_event, x_github_delivery)

    @app.post("/build", response_model=ManualBuildResponse, tags=["Manual Build"])
    async def manual_build(
        flavor: str = Form("dev", description="flavor 설정: dev, stage, prod"),
        platform: str = Form("all", description="platform 설정: all, android, ios"),
        build_name: Optional[str] = Form("", description="build name 설정"),
        build_number: Optional[str] = Form("", description="build number 설정"),
        branch_name: Optional[str] = Form("", description="branch name 설정"),
        flutter_sdk_version: Optional[str] = Form("", description="flutter sdk version 설정. 제공되지 않으면 저장소의 .fvmrc 파일 사용"),
        gradle_version: Optional[str] = Form("", description="gradle version 설정. 제공되지 않으면 .env의 GRADLE_VERSION 사용"),
        cocoapods_version: Optional[str] = Form("", description="cocoapods version 설정. 제공되지 않으면 .env의 COCOAPODS_VERSION 사용"),
        fastlane_version: Optional[str] = Form("", description="fastlane version 설정. 제공되지 않으면 .env의 FASTLANE_VERSION 사용")
    ):
        """
        수동 빌드 트리거
        
        빌드를 수동으로 트리거합니다.
        
        - **flavor**: 빌드 환경 (dev, stage, prod)
        - **platform**: 대상 플랫폼 (all, android, ios)
        - **build_name**: 커스텀 빌드 이름 (선택사항)
        - **build_number**: 커스텀 빌드 번호 (선택사항)
        - **branch_name**: 빌드할 Git 브랜치 이름 (선택사항)
        - **flutter_sdk_version**: Flutter SDK 버전 (선택사항, e.g. '3.29.3', 'stable'). 제공되지 않으면 저장소의 .fvmrc 파일 사용
        - **gradle_version**: Gradle 버전 (선택사항, e.g. '8.10', '8.11'). 제공되지 않으면 .env의 GRADLE_VERSION 사용
        - **cocoapods_version**: CocoaPods 버전 (선택사항, e.g. '1.15.2', '1.16.2'). 제공되지 않으면 .env의 COCOAPODS_VERSION 사용
        - **fastlane_version**: Fastlane 버전 (선택사항, e.g. '2.228.0'). 제공되지 않으면 .env의 FASTLANE_VERSION 사용
        """
        try:
            request_model = BuildRequest(
                flavor=flavor,
                platform=platform,
                build_name=build_name,
                build_number=build_number,
                branch_name=branch_name,
                flutter_sdk_version=flutter_sdk_version,
                gradle_version=gradle_version,
                cocoapods_version=cocoapods_version,
                fastlane_version=fastlane_version,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc

        try:
            build_id = build_service.start_build_pipeline(
                request_model.flavor,
                request_model.platform,
                "manual",
                None,
                request_model.build_name,
                request_model.build_number,
                request_model.branch_name,
                request_model.flutter_sdk_version,
                request_model.gradle_version,
                request_model.cocoapods_version,
                request_model.fastlane_version,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "manual trigger ok", "build_id": build_id}
    
    @app.post("/cleanup", response_model=CleanupResponse, tags=["Maintenance"])
    async def trigger_manual_cleanup():
        """
        수동 캐시 정리 트리거
        
        오래된 빌드 캐시와 고아 락 파일을 즉시 정리합니다.
        """
        try:
            cleanup_days = get_cache_cleanup_days()
            threading.Thread(target=manual_cleanup, args=(cleanup_days,)).start()
            return {
                "status": "ok",
                "message": f"Manual cleanup started (removing builds older than {cleanup_days} days)"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to start cleanup: {str(e)}"
            }
    
    # App startup event: 정리 스케줄러 시작 및 환경 확인
    @app.on_event("startup")
    def startup_event():
        """서버 시작 시 환경 확인 및 정리 스케줄러 실행"""
        print("🔍 Server startup diagnostics:")
        
        # SSH Agent 확인
        ssh_auth_sock = os.environ.get("SSH_AUTH_SOCK")
        if ssh_auth_sock:
            print(f"✅ SSH_AUTH_SOCK: {ssh_auth_sock}")
            if Path(ssh_auth_sock).exists():
                print(f"✅ SSH Agent socket exists")
            else:
                print(f"⚠️ SSH Agent socket does not exist!")
        else:
            print(f"❌ SSH_AUTH_SOCK not set")
            print(f"   Please start server with SSH Agent:")
            print(f"   eval $(ssh-agent -s) && ssh-add ~/.ssh/id_rsa && uvicorn main:app")
        
        # SSH 키 확인
        ssh_key = Path.home() / ".ssh" / "id_rsa"
        if ssh_key.exists():
            print(f"✅ SSH key exists: {ssh_key}")
        else:
            print(f"❌ SSH key not found: {ssh_key}")
        
        # Cleanup scheduler 시작
        cleanup_days = get_cache_cleanup_days()
        cleanup_thread = threading.Thread(
            target=start_cleanup_scheduler,
            args=(cleanup_days,),
            daemon=True
        )
        cleanup_thread.start()
        print(f"✅ Cleanup scheduler started (keeping {cleanup_days} days)")
        print(f"✅ Server ready at http://localhost:8000")
    
    return app


# FastAPI 애플리케이션 인스턴스
app = create_app()
