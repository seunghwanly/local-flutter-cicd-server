"""Webhook trigger policy resolved from environment."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class WebhookTrigger:
    flavor: str
    platform: str = "all"


class WebhookPolicy:
    """Encapsulate webhook trigger rules so they are not hardcoded in the service."""

    def __init__(self) -> None:
        self.dev_base_branch = os.environ.get("WEBHOOK_DEV_BASE_BRANCH", os.environ.get("DEV_BRANCH_NAME", "develop"))
        self.dev_head_prefix = os.environ.get("WEBHOOK_DEV_HEAD_PREFIX", "release/dev")
        self.prod_base_branch = os.environ.get("WEBHOOK_PROD_BASE_BRANCH", os.environ.get("PROD_BRANCH_NAME", "main"))
        self.prod_head_branch = os.environ.get("WEBHOOK_PROD_HEAD_BRANCH", os.environ.get("DEV_BRANCH_NAME", "develop"))
        self.prod_tag_pattern = os.environ.get("WEBHOOK_PROD_TAG_PATTERN", r"^\d+\.\d+\.\d+$")

    def resolve(self, payload: dict, event_type: str) -> Optional[WebhookTrigger]:
        if (
            event_type == "pull_request"
            and payload.get("action") == "closed"
            and payload.get("pull_request", {}).get("merged")
        ):
            base_ref = payload.get("pull_request", {}).get("base", {}).get("ref", "")
            head_ref = payload.get("pull_request", {}).get("head", {}).get("ref", "")
            if base_ref == self.dev_base_branch and head_ref.startswith(self.dev_head_prefix):
                return WebhookTrigger(flavor="dev")
            if base_ref == self.prod_base_branch and head_ref == self.prod_head_branch:
                return WebhookTrigger(flavor="prod")

        if event_type == "create" and payload.get("ref_type") == "tag":
            tag_name = payload.get("ref", "")
            if re.match(self.prod_tag_pattern, tag_name):
                return WebhookTrigger(flavor="prod")

        return None
