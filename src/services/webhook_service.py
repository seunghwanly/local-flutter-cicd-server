"""
Flutter CI/CD Server - Webhook Service

GitHub Webhook 처리 서비스
"""
import os
import hmac
import hashlib
from typing import Dict, Any

from .build_service import build_service


class WebhookService:
    """GitHub Webhook 처리 서비스"""
    
    def __init__(self):
        # GitHub Webhook Secret은 환경변수에서 반드시 직접 지정해야 함
        github_secret_env = os.environ.get("GITHUB_WEBHOOK_SECRET")
        if not github_secret_env:
            raise RuntimeError("환경변수 GITHUB_WEBHOOK_SECRET이 설정되지 않았습니다.")
        self.github_secret = github_secret_env.encode()
    
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        GitHub webhook 서명 검증
        
        Args:
            payload: 원본 페이로드 바이트
            signature: GitHub에서 전송된 서명 헤더
            
        Returns:
            서명 검증 성공 여부
        """
        if not signature:
            return False
            
        try:
            if '=' not in signature:
                return False
                
            sha_name, signature_hash = signature.split('=', 1)
            if sha_name != 'sha256':
                return False
                
            mac = hmac.new(self.github_secret, msg=payload, digestmod=hashlib.sha256)
            return hmac.compare_digest(mac.hexdigest(), signature_hash)
            
        except (ValueError, AttributeError) as e:
            print(f"⚠️ Signature verification error: {e}")
            return False
    
    def handle_webhook(self, payload: Dict[str, Any], event_type: str) -> Dict[str, str]:
        """
        GitHub Webhook 이벤트 처리
        
        Args:
            payload: Webhook 페이로드
            event_type: GitHub 이벤트 타입
            
        Returns:
            처리 결과 딕셔너리
        """
        if (
            event_type == "pull_request" and
            payload.get("action") == "closed" and
            payload.get("pull_request", {}).get("merged")
        ):
            if (payload.get("pull_request", {}).get("base", {}).get("ref") == "develop" and
                    payload.get("pull_request", {}).get("head", {}).get("ref").startswith("release-dev-v")):
                print("✅ PR merged to develop! Running CI/CD...")
                build_id = build_service.start_build_pipeline("dev", "all")
                return {"status": "ok", "build_id": build_id}

        elif (
            event_type == "create" and
            payload.get("ref_type") == "tag"
        ):
            tag_name = payload.get("ref", "")
            print(f"✅ Tag created: {tag_name}")

            if re.match(r"\d+\.\d+\.\d+", tag_name):
                print(f"✅ Valid tag format: {tag_name}")
                build_id = build_service.start_build_pipeline("prod", "all")
                return {"status": "ok", "build_id": build_id}

        return {"status": "ok"}


# 전역 인스턴스
webhook_service = WebhookService()
