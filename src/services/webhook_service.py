"""GitHub webhook processing service."""

import os
import hmac
import hashlib
from typing import Dict, Any, Optional

from ..application import WebhookPolicy
from .build_service import build_service


class WebhookService:
    """GitHub Webhook 처리 서비스"""
    
    def __init__(self):
        self.policy = WebhookPolicy()
    
    def _get_secret(self) -> Optional[bytes]:
        github_secret_env = os.environ.get("GITHUB_WEBHOOK_SECRET")
        if not github_secret_env:
            return None
        return github_secret_env.encode()
    
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        GitHub webhook 서명 검증
        
        Args:
            payload: 원본 페이로드 바이트
            signature: GitHub에서 전송된 서명 헤더
            
        Returns:
            서명 검증 성공 여부
        """
        secret = self._get_secret()
        if not secret:
            return False

        if not signature:
            return False
            
        try:
            if '=' not in signature:
                return False
                
            sha_name, signature_hash = signature.split('=', 1)
            if sha_name != 'sha256':
                return False
                
            mac = hmac.new(secret, msg=payload, digestmod=hashlib.sha256)
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
        trigger = self.policy.resolve(payload, event_type)
        if trigger:
            build_id = build_service.start_build_pipeline(trigger.flavor, trigger.platform)
            return {"status": "ok", "build_id": build_id}

        return {"status": "ok"}


# 전역 인스턴스
webhook_service = WebhookService()
