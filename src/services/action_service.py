"""External action trigger services for GitHub and Shorebird."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from typing import Any, Dict, Optional

from ..application import WebhookPolicy
from .build_service import build_service


class HmacVerifier:
    """Verify signed action payloads using provider-specific secrets."""

    def __init__(self, secret_env_var: str) -> None:
        self.secret_env_var = secret_env_var

    def verify(self, payload: bytes, signature: Optional[str], algorithms: tuple[str, ...] = ("sha256",)) -> bool:
        secret = os.environ.get(self.secret_env_var)
        if not secret or not signature or "=" not in signature:
            return False

        algorithm, signature_hash = signature.split("=", 1)
        if algorithm not in algorithms:
            return False

        digest = getattr(hashlib, algorithm, None)
        if digest is None:
            return False

        mac = hmac.new(secret.encode(), msg=payload, digestmod=digest)
        return hmac.compare_digest(mac.hexdigest(), signature_hash)


class GitHubActionService:
    """Translate GitHub webhook events into build triggers."""

    def __init__(self) -> None:
        self.policy = WebhookPolicy()
        self.verifier = HmacVerifier("GITHUB_WEBHOOK_SECRET")

    def verify_signature(
        self,
        payload: bytes,
        signature_256: Optional[str],
        signature_sha1: Optional[str] = None,
    ) -> bool:
        if signature_256 and self.verifier.verify(payload, signature_256, algorithms=("sha256",)):
            return True
        if signature_sha1 and self.verifier.verify(payload, signature_sha1, algorithms=("sha1",)):
            return True
        return False

    def handle(self, payload: Dict[str, Any], event_type: Optional[str], delivery_id: Optional[str]) -> Dict[str, str]:
        trigger = self.policy.resolve(payload, event_type or "")
        if not trigger:
            return {"status": "ignored"}

        build_id = build_service.start_build_pipeline(
            trigger.flavor,
            trigger.platform,
            trigger_source="github",
            trigger_event_id=delivery_id,
        )
        return {"status": "ok", "build_id": build_id}


class ShorebirdActionService:
    """Translate GitHub-delivered Shorebird patch events into build triggers."""

    def __init__(self) -> None:
        self.verifier = HmacVerifier("GITHUB_WEBHOOK_SECRET")
        self.prod_tag_pattern = os.environ.get("WEBHOOK_PROD_TAG_PATTERN", r"^\d+\.\d+\.\d+$")

    def verify_signature(
        self,
        payload: bytes,
        signature_256: Optional[str],
        signature_sha1: Optional[str] = None,
    ) -> bool:
        if signature_256 and self.verifier.verify(payload, signature_256, algorithms=("sha256",)):
            return True
        if signature_sha1 and self.verifier.verify(payload, signature_sha1, algorithms=("sha1",)):
            return True
        return False

    def handle(self, payload: Dict[str, Any], event_type: Optional[str], delivery_id: Optional[str]) -> Dict[str, str]:
        if not self._is_supported_tag_event(payload, event_type):
            return {"status": "ignored"}

        tag_name = self._payload_value(payload, "ref")
        build_id = build_service.start_build_pipeline(
            flavor=os.environ.get("SHOREBIRD_PATCH_FLAVOR", "prod"),
            platform=os.environ.get("SHOREBIRD_PATCH_PLATFORM", "all"),
            trigger_source="shorebird",
            trigger_event_id=delivery_id or event_type,
            build_name=tag_name,
            branch_name=os.environ.get("SHOREBIRD_PATCH_BRANCH_NAME"),
        )
        return {"status": "ok", "build_id": build_id}

    def _payload_value(self, payload: Dict[str, Any], *keys: str) -> Optional[str]:
        for key in keys:
            value = payload.get(key)
            if value is not None:
                return str(value)
        return None

    def _is_supported_tag_event(self, payload: Dict[str, Any], event_type: Optional[str]) -> bool:
        if event_type != "create":
            return False
        if payload.get("ref_type") != "tag":
            return False
        tag_name = self._payload_value(payload, "ref") or ""
        return bool(re.match(self.prod_tag_pattern, tag_name))


github_action_service = GitHubActionService()
shorebird_action_service = ShorebirdActionService()
