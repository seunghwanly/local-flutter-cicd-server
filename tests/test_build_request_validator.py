from __future__ import annotations

import unittest

from src.application.validators import BuildRequestValidator
from src.domain import BuildRequestData


class BuildRequestValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = BuildRequestValidator()

    def test_shorebird_manual_requires_release_version(self) -> None:
        request = BuildRequestData(
            flavor="prod",
            platform="ios",
            trigger_source="shorebird_manual",
            build_name=None,
            branch_name="main",
        )

        with self.assertRaisesRegex(ValueError, "build_name as release version"):
            self.validator.validate(request)

    def test_shorebird_manual_allows_android_platform(self) -> None:
        request = BuildRequestData(
            flavor="prod",
            platform="android",
            trigger_source="shorebird_manual",
            build_name="2.2.1+689",
            branch_name="main",
        )

        validated = self.validator.validate(request)

        self.assertEqual("android", validated.platform)

    def test_regular_build_can_omit_build_name(self) -> None:
        request = BuildRequestData(
            flavor="prod",
            platform="ios",
            trigger_source="manual",
            branch_name="main",
        )

        validated = self.validator.validate(request)

        self.assertIsNone(validated.build_name)


if __name__ == "__main__":
    unittest.main()
