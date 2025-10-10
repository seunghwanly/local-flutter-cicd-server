"""
Flutter CI/CD Server - API Routes

FastAPI 라우트 정의
"""
from fastapi import FastAPI, Request, Header, HTTPException
from pathlib import Path
import os
import threading

from ..models import (
    BuildRequest, BuildStatusResponse, BuildsResponse, WebhookResponse,
    ManualBuildResponse, RootResponse, CleanupResponse
)
from ..services.build_service import build_service
from ..services.webhook_service import webhook_service
from ..core.config import get_cache_cleanup_days
from ..utils.cleanup import start_cleanup_scheduler, manual_cleanup


def create_app() -> FastAPI:
    """FastAPI 애플리케이션 생성"""
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
    
    @app.post("/webhook", response_model=WebhookResponse, tags=["GitHub Webhook"])
    async def handle_webhook(
        request: Request,
        x_hub_signature_256: str = Header(None, description="GitHub webhook signature"),
        x_github_event: str = Header(None, description="GitHub event type")
    ):
        """
        GitHub Webhook 처리
        
        GitHub에서 전송되는 webhook 이벤트를 처리합니다.
        
        지원하는 이벤트:
        - PR이 develop 브랜치에 머지될 때 (dev 빌드 트리거)
        - 태그가 생성될 때 (prod 빌드 트리거)
        
        참고:
        - stage 빌드는 자동 트리거가 아닌 수동 트리거로 사용합니다.
        """
        body = await request.body()

        if not webhook_service.verify_signature(body, x_hub_signature_256):
            raise HTTPException(status_code=403, detail="Invalid signature")

        payload = await request.json()
        result = webhook_service.handle_webhook(payload, x_github_event)
        return result
    
    @app.post("/build", response_model=ManualBuildResponse, tags=["Manual Build"])
    async def manual_build(request: BuildRequest):
        """
        수동 빌드 트리거
        
        빌드를 수동으로 트리거합니다.
        
        - **flavor**: 빌드 환경 (dev, stage, prod)
        - **platform**: 대상 플랫폼 (all, android, ios)
        - **build_name**: 커스텀 빌드 이름 (선택사항)
        - **build_number**: 커스텀 빌드 번호 (선택사항)
        - **branch_name**: 빌드할 Git 브랜치 이름 (선택사항)
        - **fvm_flavor**: FVM flavor (선택사항)
        """
        build_id = build_service.start_build_pipeline(
            request.flavor, 
            request.platform, 
            request.build_name, 
            request.build_number, 
            request.branch_name,
            request.fvm_flavor
        )
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
