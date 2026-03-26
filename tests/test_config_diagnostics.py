from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from src.internal.application.config_diagnostics import ConfigDiagnostics
from src.internal.domain import BuildRequestData


class ConfigDiagnosticsTests(unittest.TestCase):
    def test_ephemeral_keychain_strategy_is_ready_without_startup_cache(self) -> None:
        diagnostics = ConfigDiagnostics()

        with patch.dict(
            os.environ,
            {
                "REPO_URL": "git@github.com:org/app.git",
                "DEV_FASTLANE_LANE": "beta",
                "DEV_BRANCH_NAME": "develop",
                "MATCH_PASSWORD": "match-secret",
            },
            clear=True,
        ):
            result = diagnostics.get_build_diagnostics(
                BuildRequestData(flavor="dev", platform="ios", branch_name="develop")
            )

        self.assertTrue(result.ready)
        self.assertNotIn("keychain: keychain not validated at startup", result.missing)

    def test_validate_keychain_on_startup_succeeds_for_ephemeral_strategy(self) -> None:
        diagnostics = ConfigDiagnostics()

        with patch.dict(os.environ, {}, clear=True):
            result = diagnostics.validate_keychain_on_startup()

        self.assertTrue(result.ready)
        self.assertEqual("ephemeral", result.details["strategy"])
        self.assertEqual([], result.missing)

    def test_validate_keychain_on_startup_requires_password_for_configured_keychain(self) -> None:
        diagnostics = ConfigDiagnostics()

        with tempfile.TemporaryDirectory() as home:
            keychain_dir = Path(home) / "Library" / "Keychains"
            keychain_dir.mkdir(parents=True, exist_ok=True)
            (keychain_dir / "login.keychain-db").write_text("", encoding="utf-8")

            with (
                patch.dict(
                    os.environ,
                    {
                        "KEYCHAIN_NAME": "login.keychain",
                        "KEYCHAIN_PASSWORD": "",
                    },
                    clear=True,
                ),
                patch("pathlib.Path.home", return_value=Path(home)),
                patch(
                    "subprocess.run",
                    return_value=CompletedProcess(
                        args=["security", "find-identity"],
                        returncode=0,
                        stdout="  1) ABCDEF1234567890 \"Apple Distribution: Example\"\n     1 valid identities found\n",
                    ),
                ),
            ):
                result = diagnostics.validate_keychain_on_startup()

        self.assertFalse(result.ready)
        self.assertIn("KEYCHAIN_PASSWORD (required for configured keychain)", result.missing)


if __name__ == "__main__":
    unittest.main()
