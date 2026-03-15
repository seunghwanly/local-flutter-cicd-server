from __future__ import annotations

import unittest
from unittest.mock import Mock

from src.application.build_status_presenter import BuildStatusPresenter
from src.domain import BuildStatus
from src.domain import BuildJob, BuildRequestData
from src.domain.builds import BuildStatus


class FakeProcess:
    def __init__(self, returncode: int | None) -> None:
        self.returncode = returncode

    def poll(self) -> int | None:
        return self.returncode


class BuildStatusPresenterTests(unittest.TestCase):
    def test_detail_includes_stage_timeline_without_setup_process(self) -> None:
        request = BuildRequestData(flavor="dev", platform="ios")
        job = BuildJob.create(
            build_id="build-1",
            request=request,
            branch_name="develop",
            queue_key="dev-develop",
        )
        job.mark_stage_completed("request_validated", "validated")
        job.mark_stage_completed("environment_prepared", "ready")

        detail = BuildStatusPresenter().detail(job, "/tmp/build.log")

        self.assertNotIn("setup", detail["processes"])
        self.assertTrue(any(stage["name"] == "request_validated" for stage in detail["stages"]))
        self.assertEqual("/tmp/build.log", detail["log_file_path"])
        self.assertEqual("manual", detail["trigger_source"])
        self.assertIsNone(detail["trigger_event_id"])

    def test_detail_marks_build_failed_when_any_stage_failed(self) -> None:
        request = BuildRequestData(flavor="prod", platform="all")
        job = BuildJob.create(
            build_id="build-2",
            request=request,
            branch_name="main",
            queue_key="prod-main",
        )
        job.status = BuildStatus.COMPLETED
        job.mark_stage_completed("android_build", "Android completed")
        job.mark_stage_failed("ios_build", "Exit code 1")

        detail = BuildStatusPresenter().detail(job, None)
        summary = BuildStatusPresenter().summary(job)

        self.assertEqual("failed", detail["status"])
        self.assertEqual("failed", summary["status"])

    def test_detail_marks_build_failed_when_process_return_code_is_non_zero(self) -> None:
        request = BuildRequestData(flavor="prod", platform="android")
        job = BuildJob.create(
            build_id="build-3",
            request=request,
            branch_name="main",
            queue_key="prod-main",
        )
        job.status = BuildStatus.COMPLETED
        job.processes["android"] = FakeProcess(returncode=1)

        detail = BuildStatusPresenter().detail(job, None)
        summary = BuildStatusPresenter().summary(job)

        self.assertEqual("failed", detail["status"])
        self.assertEqual("failed", summary["status"])
    def test_summary_includes_platform_statuses_for_all_builds(self) -> None:
        request = BuildRequestData(flavor="dev", platform="all")
        job = BuildJob.create(
            build_id="build-2",
            request=request,
            branch_name="develop",
            queue_key="dev-develop",
        )
        job.mark_stage_completed("android_toolchain_ready", "Android ready")
        job.mark_stage_completed("android_build", "Android ok")
        job.mark_stage_failed("ios_build", "Exit code 1")
        job.status = BuildStatus.FAILED

        summary = BuildStatusPresenter().summary(job)

        self.assertEqual("completed", summary["platform_statuses"]["android"]["status"])
        self.assertEqual("failed", summary["platform_statuses"]["ios"]["status"])
        self.assertTrue(any(stage["name"] == "android_build" for stage in summary["stages"]))

    def test_detail_marks_platform_running_when_process_is_active(self) -> None:
        request = BuildRequestData(flavor="dev", platform="android")
        job = BuildJob.create(
            build_id="build-3",
            request=request,
            branch_name="develop",
            queue_key="dev-develop",
        )
        process = Mock()
        process.poll.return_value = None
        process.returncode = None
        job.processes["android"] = process

        detail = BuildStatusPresenter().detail(job, None)

        self.assertEqual("running", detail["platform_statuses"]["android"]["status"])
        self.assertTrue(detail["processes"]["android"]["running"])


if __name__ == "__main__":
    unittest.main()
