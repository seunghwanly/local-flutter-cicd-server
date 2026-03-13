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
        self.dev_base_prefix = os.environ.get("WEBHOOK_DEV_BASE_PREFIX", "release/dev")
        self.prod_tag_pattern = os.environ.get("WEBHOOK_PROD_TAG_PATTERN", r"^\d+\.\d+\.\d+$")

    def resolve(self, payload: dict, event_type: str) -> Optional[WebhookTrigger]:
        if (
            event_type == "pull_request"
            and payload.get("action") == "closed"
            and payload.get("pull_request", {}).get("merged")
        ):
            base_ref = payload.get("pull_request", {}).get("base", {}).get("ref", "")
            if base_ref.startswith(self.dev_base_prefix):
                return WebhookTrigger(flavor="dev")

        if event_type == "create" and payload.get("ref_type") == "tag":
            tag_name = payload.get("ref", "")
            if re.match(self.prod_tag_pattern, tag_name):
                return WebhookTrigger(flavor="prod")

        return None
