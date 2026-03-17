from __future__ import annotations

import hashlib
import hmac
import os
import unittest
from unittest.mock import patch

from src.models import BuildPipelineRequestDto
from src.internal.application.webhook_policy import WebhookPolicy
from src.services.trigger_service import GitHubActionService, ShorebirdActionService


class GitHubActionServiceTests(unittest.TestCase):
    def test_verify_signature_uses_hmac_sha256(self) -> None:
        payload = b'{"action":"closed"}'
        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "topsecret"}, clear=False):
            expected = hmac.new(b"topsecret", msg=payload, digestmod=hashlib.sha256).hexdigest()
            service = GitHubActionService()

            self.assertTrue(service.verify_signature(payload, f"sha256={expected}"))
            self.assertFalse(service.verify_signature(payload, "sha256=invalid"))

    def test_verify_signature_accepts_sha1_fallback(self) -> None:
        payload = b'{"action":"closed"}'
        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "topsecret"}, clear=False):
            expected = hmac.new(b"topsecret", msg=payload, digestmod=hashlib.sha1).hexdigest()
            service = GitHubActionService()

            self.assertTrue(service.verify_signature(payload, None, f"sha1={expected}"))

    def test_handle_returns_ignored_when_policy_does_not_match(self) -> None:
        service = GitHubActionService()

        result = service.handle({}, "push", "delivery-1")

        self.assertEqual({"status": "ignored"}, result)


class WebhookPolicyTests(unittest.TestCase):
    def test_resolve_dev_for_merge_into_release_dev_prefix(self) -> None:
        payload = {
            "action": "closed",
            "pull_request": {
                "merged": True,
                "base": {"ref": "release/dev-hotfix"},
                "head": {"ref": "feature/offline-coupon"},
            },
        }

        trigger = WebhookPolicy().resolve(payload, "pull_request")

        self.assertIsNotNone(trigger)
        self.assertEqual("dev", trigger.flavor)

    def test_resolve_returns_none_for_develop_to_main_merge(self) -> None:
        payload = {
            "action": "closed",
            "pull_request": {
                "merged": True,
                "base": {"ref": "main"},
                "head": {"ref": "develop"},
            },
        }

        trigger = WebhookPolicy().resolve(payload, "pull_request")

        self.assertIsNone(trigger)


class ShorebirdActionServiceTests(unittest.TestCase):
    def test_verify_signature_accepts_same_github_secret(self) -> None:
        payload = b'{"ref":"1.2.3"}'
        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "topsecret"}, clear=False):
            expected = hmac.new(b"topsecret", msg=payload, digestmod=hashlib.sha256).hexdigest()
            service = ShorebirdActionService()

            self.assertTrue(service.verify_signature(payload, f"sha256={expected}"))

    @patch("src.services.trigger_service.build_service.start_build_pipeline")
    def test_handle_uses_tag_event_for_patch_trigger(self, start_build_pipeline) -> None:
        start_build_pipeline.return_value = "build-123"
        payload = {"ref_type": "tag", "ref": "1.2.3"}
        with patch.dict(
            os.environ,
            {
                "SHOREBIRD_PATCH_FLAVOR": "prod",
                "SHOREBIRD_PATCH_PLATFORM": "ios",
                "SHOREBIRD_PATCH_BRANCH_NAME": "main",
            },
            clear=False,
        ):
            service = ShorebirdActionService()

            result = service.handle(payload, "create", "shorebird-1")

        self.assertEqual({"status": "ok", "build_id": "build-123"}, result)
        start_build_pipeline.assert_called_once_with(
            BuildPipelineRequestDto(
                flavor="prod",
                platform="ios",
                trigger_source="shorebird",
                trigger_event_id="shorebird-1",
                build_name="1.2.3",
                build_number=None,
                branch_name="main",
            )
        )

    @patch("src.services.trigger_service.build_service.start_build_pipeline")
    def test_handle_prefers_payload_build_metadata_when_present(self, start_build_pipeline) -> None:
        start_build_pipeline.return_value = "build-456"
        payload = {
            "ref_type": "tag",
            "ref": "1.2.3",
            "payload": {
                "build_name": "2.2.1",
                "build_number": "689",
            },
        }
        with patch.dict(
            os.environ,
            {
                "SHOREBIRD_PATCH_FLAVOR": "prod",
                "SHOREBIRD_PATCH_PLATFORM": "ios",
                "SHOREBIRD_PATCH_BRANCH_NAME": "main",
            },
            clear=False,
        ):
            service = ShorebirdActionService()

            result = service.handle(payload, "create", "shorebird-3")

        self.assertEqual({"status": "ok", "build_id": "build-456"}, result)
        start_build_pipeline.assert_called_once_with(
            BuildPipelineRequestDto(
                flavor="prod",
                platform="ios",
                trigger_source="shorebird",
                trigger_event_id="shorebird-3",
                build_name="2.2.1",
                build_number="689",
                branch_name="main",
            )
        )

    @patch("src.services.trigger_service.build_service.start_build_pipeline")
    def test_handle_accepts_flavor_from_payload_alias(self, start_build_pipeline) -> None:
        start_build_pipeline.return_value = "build-789"
        payload = {
            "ref_type": "tag",
            "ref": "1.2.3",
            "payload": {
                "flavor": "stg",
                "build_name": "2.2.1",
                "build_number": "689",
            },
        }
        with patch.dict(
            os.environ,
            {
                "SHOREBIRD_PATCH_FLAVOR": "prod",
                "SHOREBIRD_PATCH_PLATFORM": "ios",
                "SHOREBIRD_PATCH_BRANCH_NAME": "main",
            },
            clear=False,
        ):
            service = ShorebirdActionService()

            result = service.handle(payload, "create", "shorebird-4")

        self.assertEqual({"status": "ok", "build_id": "build-789"}, result)
        start_build_pipeline.assert_called_once_with(
            BuildPipelineRequestDto(
                flavor="stage",
                platform="ios",
                trigger_source="shorebird",
                trigger_event_id="shorebird-4",
                build_name="2.2.1",
                build_number="689",
                branch_name="main",
            )
        )

    @patch("src.services.trigger_service.build_service.start_build_pipeline")
    def test_handle_ignores_non_tag_event(self, start_build_pipeline) -> None:
        service = ShorebirdActionService()

        result = service.handle({"action": "closed"}, "pull_request", "shorebird-2")

        self.assertEqual({"status": "ignored"}, result)
        start_build_pipeline.assert_not_called()


if __name__ == "__main__":
    unittest.main()
