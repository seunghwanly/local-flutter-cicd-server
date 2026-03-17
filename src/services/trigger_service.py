"""External action trigger services for GitHub and Shorebird."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from typing import Any, Dict, Optional

from ..internal.application import WebhookPolicy
from ..models import BuildPipelineRequestDto
from .build_pipeline_service import BuildService, build_service


class HmacVerifier:
    """Verify signed action payloads using provider-specific secrets."""

    def __init__(self, secret: Optional[str]) -> None:
        self.secret = secret

    def verify(self, payload: bytes, signature: Optional[str], algorithms: tuple[str, ...] = ("sha256",)) -> bool:
        if not self.secret or not signature or "=" not in signature:
            return False

        algorithm, signature_hash = signature.split("=", 1)
        if algorithm not in algorithms:
            return False

        digest = getattr(hashlib, algorithm, None)
        if digest is None:
            return False

        mac = hmac.new(self.secret.encode(), msg=payload, digestmod=digest)
        return hmac.compare_digest(mac.hexdigest(), signature_hash)


class GitHubActionService:
    """Translate GitHub webhook events into build triggers."""

    def __init__(
        self,
        build_service: BuildService | None = None,
        webhook_secret: Optional[str] = None,
    ) -> None:
        self.policy = WebhookPolicy()
        self.build_service = build_service or globals()["build_service"]
        self.verifier = HmacVerifier(webhook_secret or os.environ.get("GITHUB_WEBHOOK_SECRET"))

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

        build_id = self.build_service.start_build_pipeline(
            BuildPipelineRequestDto(
                flavor=trigger.flavor,
                platform=trigger.platform,
                trigger_source="github",
                trigger_event_id=delivery_id,
            )
        )
        return {"status": "ok", "build_id": build_id}


class ShorebirdActionService:
    """Translate GitHub-delivered Shorebird tag events into build triggers."""

    FLAVOR_ALIASES = {
        "dev": "dev",
        "development": "dev",
        "stg": "stage",
        "stage": "stage",
        "prd": "prod",
        "prod": "prod",
        "production": "prod",
    }

    def __init__(
        self,
        build_service: BuildService | None = None,
        webhook_secret: Optional[str] = None,
        prod_tag_pattern: Optional[str] = None,
        default_flavor: str = "prod",
        default_platform: str = "ios",
        default_branch_name: Optional[str] = None,
    ) -> None:
        self.build_service = build_service or globals()["build_service"]
        self.verifier = HmacVerifier(webhook_secret or os.environ.get("GITHUB_WEBHOOK_SECRET"))
        self.prod_tag_pattern = prod_tag_pattern or os.environ.get("WEBHOOK_PROD_TAG_PATTERN", r"^\d+\.\d+\.\d+$")
        self.default_flavor = default_flavor or os.environ.get("SHOREBIRD_PATCH_FLAVOR", "prod")
        self.default_platform = default_platform or os.environ.get("SHOREBIRD_PATCH_PLATFORM", "ios")
        self.default_branch_name = default_branch_name or os.environ.get("SHOREBIRD_PATCH_BRANCH_NAME")

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

        flavor = self._resolve_flavor(payload)
        build_name = self._extract_webhook_value(payload, "build_name")
        build_number = self._extract_webhook_value(payload, "build_number")

        build_id = self.build_service.start_build_pipeline(
            BuildPipelineRequestDto(
                flavor=flavor,
                platform=self.default_platform,
                trigger_source="shorebird",
                trigger_event_id=delivery_id or event_type,
                build_name=build_name or self._payload_value(payload, "ref"),
                build_number=build_number,
                branch_name=self.default_branch_name,
            )
        )
        return {"status": "ok", "build_id": build_id}

    def _payload_value(self, payload: Dict[str, Any], *keys: str) -> Optional[str]:
        for key in keys:
            value = payload.get(key)
            if value is not None:
                return str(value)
        return None

    def _extract_webhook_value(self, payload: Dict[str, Any], key: str) -> Optional[str]:
        value = self._payload_value(payload, key)
        if value is not None:
            return value

        for container_key in ("payload", "inputs", "client_payload"):
            nested_payload = payload.get(container_key)
            if isinstance(nested_payload, dict):
                value = self._payload_value(nested_payload, key)
                if value is not None:
                    return value
        return None

    def _resolve_flavor(self, payload: Dict[str, Any]) -> str:
        requested_flavor = self._extract_webhook_value(payload, "flavor")
        if requested_flavor is None:
            return self.default_flavor

        normalized = self.FLAVOR_ALIASES.get(requested_flavor.strip().lower())
        if normalized is not None:
            return normalized

        return self.default_flavor

    def _is_supported_tag_event(self, payload: Dict[str, Any], event_type: Optional[str]) -> bool:
        if event_type != "create":
            return False
        if payload.get("ref_type") != "tag":
            return False
        tag_name = self._payload_value(payload, "ref") or ""
        return bool(re.match(self.prod_tag_pattern, tag_name))


github_action_service = GitHubActionService()
shorebird_action_service = ShorebirdActionService()
