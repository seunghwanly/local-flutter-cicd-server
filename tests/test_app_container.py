from __future__ import annotations

import unittest

from src.core.app import build_container
from src.core.settings import AppSettings


class AppContainerTests(unittest.TestCase):
    def test_build_container_shares_startup_diagnostics_with_build_service(self) -> None:
        container = build_container(AppSettings())

        self.assertIs(
            container.diagnostics,
            container.build_service.orchestrator.config_diagnostics,
        )


if __name__ == "__main__":
    unittest.main()
